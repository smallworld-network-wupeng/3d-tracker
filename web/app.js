/* global Cesium */
(async () => {
  const $ = (id) => document.getElementById(id);
  const renderConfig = await fetch("/render-config.json")
    .then((response) => response.ok ? response.json() : {})
    .catch(() => ({}));
  const setting = (name, fallback) => Number.isFinite(renderConfig[name]) ? renderConfig[name] : fallback;
  document.documentElement.style.setProperty("--metric-scale", setting("metric_scale", 1));
  // The config stores widths in pixels at the 1080px short-edge reference.
  document.documentElement.style.setProperty(
    "--portrait-profile-width", `${setting("portrait_profile_width", 520) / 10}rem`
  );
  document.documentElement.style.setProperty(
    "--landscape-title-width", `${setting("landscape_title_width", 460) / 10}rem`
  );
  const TERRAIN_SIZE = 256;
  const TERRAIN_MAX_LEVEL = 14;
  const TERRAIN_EXAGGERATION = setting("terrain_exaggeration", 1.35);
  const INTRO_RATIO = setting("intro_ratio", 0.07);
  const OUTRO_RATIO = setting("outro_ratio", 0.07);
  const CAMERA_PITCH_DEG = setting("camera_pitch_deg", -57);
  const CAMERA_RANGE_M = setting("camera_range_m", 9500);
  const AUTO_CAMERA_RANGE = renderConfig.auto_camera_range !== false;
  const CAMERA_MIN_RANGE_M = setting("camera_min_range_m", window.innerHeight > window.innerWidth ? 3000 : 2200);
  const CAMERA_MAX_RANGE_M = setting("camera_max_range_m", 120000);
  const CAMERA_FIT_HORIZONTAL = setting("camera_fit_horizontal", window.innerHeight > window.innerWidth ? 0.78 : 0.74);
  const CAMERA_FIT_VERTICAL = setting("camera_fit_vertical", window.innerHeight > window.innerWidth ? 0.62 : 0.74);
  const CAMERA_FIT_PADDING = setting("camera_fit_padding", 1.10);
  const CAMERA_SCREEN_Y = setting("camera_screen_y", window.innerHeight > window.innerWidth ? 0.08 : 0.14);
  const CAMERA_LOOK_AHEAD_M = setting("camera_look_ahead_m", 500);
  const CAMERA_TARGET_LEAD = setting("camera_target_lead", 0.65);
  const ORBIT_START_DEG = setting("orbit_start_deg", 18);
  const ORBIT_DEGREES = setting("orbit_degrees", 70);
  const terrainCanvas = document.createElement("canvas");
  terrainCanvas.width = TERRAIN_SIZE;
  terrainCanvas.height = TERRAIN_SIZE;
  const terrainContext = terrainCanvas.getContext("2d", { willReadFrequently: true });
  const terrainCache = new Map();

  async function decodeTerrainTile(x, y, level) {
    const sourceLevel = Math.min(level, TERRAIN_MAX_LEVEL);
    const detailScale = 2 ** (level - sourceLevel);
    const sourceX = Math.floor(x / detailScale);
    const sourceY = Math.floor(y / detailScale);
    const cacheKey = `${sourceLevel}/${sourceX}/${sourceY}/${level}/${x}/${y}`;
    if (terrainCache.has(cacheKey)) return terrainCache.get(cacheKey);
    const task = (async () => {
      const response = await fetch(`/terrain/${sourceLevel}/${sourceX}/${sourceY}.png`);
      if (!response.ok) return new Float32Array(TERRAIN_SIZE * TERRAIN_SIZE);
      const bitmap = await createImageBitmap(await response.blob());
      const sourceSize = TERRAIN_SIZE / detailScale;
      const offsetX = (x % detailScale) * sourceSize;
      const offsetY = (y % detailScale) * sourceSize;
      terrainContext.clearRect(0, 0, TERRAIN_SIZE, TERRAIN_SIZE);
      terrainContext.drawImage(bitmap, offsetX, offsetY, sourceSize, sourceSize, 0, 0, TERRAIN_SIZE, TERRAIN_SIZE);
      bitmap.close();
      const rgba = terrainContext.getImageData(0, 0, TERRAIN_SIZE, TERRAIN_SIZE).data;
      const heights = new Float32Array(TERRAIN_SIZE * TERRAIN_SIZE);
      for (let pixel = 0, output = 0; pixel < rgba.length; pixel += 4, output += 1) {
        heights[output] = rgba[pixel] * 256 + rgba[pixel + 1] + rgba[pixel + 2] / 256 - 32768;
      }
      window.__TERRAIN_TILE_COUNT__ = (window.__TERRAIN_TILE_COUNT__ || 0) + 1;
      return heights;
    })();
    terrainCache.set(cacheKey, task);
    return task;
  }

  const terrainProvider = new Cesium.CustomHeightmapTerrainProvider({
    width: TERRAIN_SIZE,
    height: TERRAIN_SIZE,
    tilingScheme: new Cesium.WebMercatorTilingScheme(),
    callback: decodeTerrainTile,
    credit: "Elevation: AWS Terrain Tiles / SRTM",
  });
  const viewer = new Cesium.Viewer("cesiumContainer", {
    animation: false, timeline: false, baseLayerPicker: false, geocoder: false,
    homeButton: false, sceneModePicker: false, navigationHelpButton: false,
    infoBox: false, selectionIndicator: false, fullscreenButton: false,
    baseLayer: false, requestRenderMode: true, maximumRenderTimeChange: Infinity,
    contextOptions: { webgl: { preserveDrawingBuffer: true } }, terrainProvider,
  });
  window.__RENDER_ERROR__ = null;
  viewer.scene.renderError.addEventListener((_scene, error) => {
    const details = error && Object.fromEntries(
      Object.getOwnPropertyNames(error).map((key) => [key, error[key]])
    );
    window.__RENDER_ERROR__ = error?.stack || error?.message || JSON.stringify(details) || String(error);
  });
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#17252b");
  viewer.scene.globe.enableLighting = true;
  viewer.scene.globe.depthTestAgainstTerrain = true;
  viewer.scene.verticalExaggeration = TERRAIN_EXAGGERATION;
  viewer.shadows = false;
  viewer.terrainShadows = Cesium.ShadowMode.DISABLED;
  viewer.scene.fog.enabled = true;
  viewer.scene.skyAtmosphere.show = true;
  viewer.scene.screenSpaceCameraController.enableInputs = false;
  viewer.scene.postProcessStages.fxaa.enabled = true;

  try {
    const naturalEarth = await Cesium.TileMapServiceImageryProvider.fromUrl(
      Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII")
    );
    viewer.imageryLayers.addImageryProvider(naturalEarth);
  } catch (error) {
    console.warn("Natural Earth imagery unavailable", error);
  }

  const payload = await fetch("/track.json").then((response) => {
    if (!response.ok) throw new Error(`轨迹载入失败：HTTP ${response.status}`);
    return response.json();
  });
  const { metadata, points, metrics = [] } = payload;
  const imageryMargin = setting("imagery_margin_deg", 0.15);
  viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({
    url: "/imagery/{z}/{x}/{y}.jpg",
    minimumLevel: 8,
    maximumLevel: 14,
    rectangle: Cesium.Rectangle.fromDegrees(
      metadata.bounds[0] - imageryMargin,
      metadata.bounds[1] - imageryMargin,
      metadata.bounds[2] + imageryMargin,
      metadata.bounds[3] + imageryMargin
    ),
    credit: "Imagery © Esri",
  }));
  const positions = points.map((point) => Cesium.Cartesian3.fromDegrees(
    point[0], point[1], point[2] * TERRAIN_EXAGGERATION + 60
  ));
  const routeCanvas = $("routeOverlay");
  routeCanvas.width = routeCanvas.clientWidth;
  routeCanvas.height = routeCanvas.clientHeight;
  const routeContext = routeCanvas.getContext("2d");
  const runner = viewer.entities.add({
    position: positions[0],
    point: {
      pixelSize: 11,
      color: Cesium.Color.WHITE,
      outlineColor: Cesium.Color.fromCssColorString("#ffd43b"),
      outlineWidth: 3,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
    },
  });

  $("activityName").textContent = metadata.name;
  $("persistentActivityName").textContent = metadata.name;
  $("persistentSource").textContent = metadata.source;
  const startDate = new Date(metadata.start);
  $("activityDate").textContent = startDate.toLocaleDateString("zh-CN", {
    year: "numeric", month: "long", day: "numeric", timeZone: "Asia/Shanghai"
  });
  const reportedDistance = metadata.reported_distance_km || metadata.distance_m / 1000;
  const reportedGain = metadata.reported_gain_m || metadata.max_altitude_m - metadata.min_altitude_m;
  $("introSummary").textContent = `${reportedDistance.toFixed(1)} KM  ·  ${metadata.reported_duration || formatDuration(metadata.duration_seconds)}  ·  +${Math.round(reportedGain)} M`;
  const profileCanvas = $("elevationProfile");
  const profileContext = profileCanvas.getContext("2d");

  function drawElevationProfile(progress, currentPoint) {
    const width = profileCanvas.width;
    const height = profileCanvas.height;
    const padding = 5;
    const altitudeSpan = Math.max(1, metadata.max_altitude_m - metadata.min_altitude_m);
    const pointXY = (point) => [
      padding + (point[4] / metadata.distance_m) * (width - padding * 2),
      height - padding - ((point[2] - metadata.min_altitude_m) / altitudeSpan) * (height - padding * 2),
    ];
    profileContext.clearRect(0, 0, width, height);
    const gradient = profileContext.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, "rgba(255,255,255,.64)");
    gradient.addColorStop(1, "rgba(255,255,255,.08)");
    profileContext.beginPath();
    profileContext.moveTo(padding, height - padding);
    points.forEach((point) => profileContext.lineTo(...pointXY(point)));
    profileContext.lineTo(width - padding, height - padding);
    profileContext.closePath();
    profileContext.fillStyle = gradient;
    profileContext.fill();
    const strokeProfile = (color, lineWidth) => {
      profileContext.beginPath();
      points.forEach((point, index) => {
        const xy = pointXY(point);
        if (index === 0) profileContext.moveTo(...xy); else profileContext.lineTo(...xy);
      });
      profileContext.strokeStyle = color;
      profileContext.lineWidth = lineWidth;
      profileContext.stroke();
    };
    strokeProfile("rgba(255,255,255,.92)", 2.5);
    profileContext.save();
    profileContext.beginPath();
    profileContext.rect(0, 0, Math.max(0, progress) * width, height);
    profileContext.clip();
    strokeProfile("#ffd43b", 4);
    profileContext.restore();
    const current = pointXY(currentPoint);
    profileContext.beginPath();
    profileContext.arc(current[0], current[1], 4.5, 0, Math.PI * 2);
    profileContext.fillStyle = "#ffd43b";
    profileContext.fill();
    profileContext.strokeStyle = "white";
    profileContext.lineWidth = 2;
    profileContext.stroke();
  }

  function drawRouteOverlay(lastIndex, currentPosition) {
    routeContext.clearRect(0, 0, routeCanvas.width, routeCanvas.height);
    routeContext.beginPath();
    let started = false;
    for (let index = 0; index <= lastIndex; index += 1) {
      const screen = Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene, positions[index]);
      if (!screen || !Number.isFinite(screen.x) || !Number.isFinite(screen.y)) continue;
      if (!started) {
        routeContext.moveTo(screen.x, screen.y);
        started = true;
      } else {
        routeContext.lineTo(screen.x, screen.y);
      }
    }
    const currentScreen = Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene, currentPosition);
    if (started && currentScreen && Number.isFinite(currentScreen.x) && Number.isFinite(currentScreen.y)) {
      routeContext.lineTo(currentScreen.x, currentScreen.y);
    }
    routeContext.lineJoin = "round";
    routeContext.lineCap = "round";
    routeContext.lineWidth = 4;
    routeContext.strokeStyle = "#ffd43b";
    routeContext.shadowColor = "rgba(255,154,36,.7)";
    routeContext.shadowBlur = 5;
    routeContext.stroke();
    routeContext.shadowBlur = 0;
  }

  function formatDuration(seconds) {
    const value = Math.max(0, Math.round(seconds));
    const h = String(Math.floor(value / 3600)).padStart(2, "0");
    const m = String(Math.floor((value % 3600) / 60)).padStart(2, "0");
    const s = String(value % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
  }

  function formatPace(speed) {
    if (!Number.isFinite(speed) || speed < 0.12) return `--'--"`;
    const totalSeconds = Math.min(99 * 60 + 59, Math.round(1000 / speed));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = String(totalSeconds % 60).padStart(2, "0");
    return `${minutes}'${seconds}"`;
  }

  function metricSampleAtTime(seconds) {
    if (!metrics.length) return { heartRate: null, speed: null };
    let low = 0, high = metrics.length - 1;
    while (low < high) {
      const mid = Math.ceil((low + high) / 2);
      if (metrics[mid][0] <= seconds) low = mid; else high = mid - 1;
    }
    if (low >= metrics.length - 1) {
      return { heartRate: metrics[low][1], speed: metrics[low][2] };
    }
    const lower = metrics[low];
    const upper = metrics[low + 1];
    const duration = upper[0] - lower[0];
    const fraction = duration > 0 ? Cesium.Math.clamp((seconds - lower[0]) / duration, 0, 1) : 0;
    const interpolateMetric = (a, b) => {
      if (Number.isFinite(a) && Number.isFinite(b)) return Cesium.Math.lerp(a, b, fraction);
      return Number.isFinite(a) ? a : (Number.isFinite(b) ? b : null);
    };
    return {
      heartRate: interpolateMetric(lower[1], upper[1]),
      speed: interpolateMetric(lower[2], upper[2]),
    };
  }

  function trackIndexAt(seconds) {
    let low = 0, high = points.length - 1;
    while (low < high) {
      const mid = Math.ceil((low + high) / 2);
      if (points[mid][3] <= seconds) low = mid; else high = mid - 1;
    }
    return low;
  }

  function trackIndexAtDistance(distance) {
    const target = Cesium.Math.clamp(distance, 0, metadata.distance_m);
    let low = 0, high = points.length - 1;
    while (low < high) {
      const mid = Math.ceil((low + high) / 2);
      if (points[mid][4] <= target) low = mid; else high = mid - 1;
    }
    return low;
  }

  function interpolatePoint(lower, upper, fraction) {
    return [
      Cesium.Math.lerp(lower[0], upper[0], fraction),
      Cesium.Math.lerp(lower[1], upper[1], fraction),
      Cesium.Math.lerp(lower[2], upper[2], fraction),
      Cesium.Math.lerp(lower[3], upper[3], fraction),
      Cesium.Math.lerp(lower[4], upper[4], fraction),
    ];
  }

  function pointPosition(point) {
    return Cesium.Cartesian3.fromDegrees(
      point[0], point[1], point[2] * TERRAIN_EXAGGERATION + 60
    );
  }

  function trackSampleAtTime(seconds) {
    const lowerIndex = trackIndexAt(seconds);
    if (lowerIndex >= points.length - 1) {
      return { point: points[points.length - 1], position: positions[positions.length - 1], lowerIndex };
    }
    const lower = points[lowerIndex];
    const upper = points[lowerIndex + 1];
    const duration = upper[3] - lower[3];
    const fraction = duration > 0 ? Cesium.Math.clamp((seconds - lower[3]) / duration, 0, 1) : 0;
    const point = interpolatePoint(lower, upper, fraction);
    return { point, position: pointPosition(point), lowerIndex };
  }

  function positionAtDistance(distance) {
    const lowerIndex = trackIndexAtDistance(distance);
    if (lowerIndex >= points.length - 1) return positions[positions.length - 1];
    const lower = points[lowerIndex];
    const upper = points[lowerIndex + 1];
    const segmentDistance = upper[4] - lower[4];
    const fraction = segmentDistance > 0
      ? Cesium.Math.clamp((distance - lower[4]) / segmentDistance, 0, 1)
      : 0;
    return pointPosition(interpolatePoint(lower, upper, fraction));
  }

  const trackBounds = Cesium.BoundingSphere.fromPoints(positions);
  const center = Cesium.Cartesian3.clone(trackBounds.center);
  const diagonal = new Cesium.EllipsoidGeodesic(
    Cesium.Cartographic.fromDegrees(metadata.bounds[0], metadata.bounds[1]),
    Cesium.Cartographic.fromDegrees(metadata.bounds[2], metadata.bounds[3])
  ).surfaceDistance;

  // Find the shortest camera range that keeps the requested track points inside
  // the configured fraction of the viewport. Unlike a fixed range or a simple
  // geographic diagonal, this accounts for output aspect ratio, camera heading,
  // pitch, elevation, and the fact that the follow camera is not at track center.
  function rangeForTarget(target, heading, pitch, lastIndex, currentPosition) {
    viewer.camera.lookAt(target, new Cesium.HeadingPitchRange(
      heading, pitch, Math.max(1000, CAMERA_MIN_RANGE_M)
    ));
    const frustum = viewer.camera.frustum;
    const tanHalfVertical = Math.tan(frustum.fovy * 0.5);
    const tanHalfHorizontal = tanHalfVertical * frustum.aspectRatio;
    const horizontalLimit = Cesium.Math.clamp(CAMERA_FIT_HORIZONTAL, 0.1, 0.95) * tanHalfHorizontal;
    const verticalLimit = Cesium.Math.clamp(CAMERA_FIT_VERTICAL, 0.1, 0.95) * tanHalfVertical;
    const direction = viewer.camera.directionWC;
    const right = viewer.camera.rightWC;
    const up = viewer.camera.upWC;
    const offset = new Cesium.Cartesian3();
    let requiredRange = 0;

    const include = (position) => {
      Cesium.Cartesian3.subtract(position, target, offset);
      const forward = Cesium.Cartesian3.dot(offset, direction);
      const horizontal = Math.abs(Cesium.Cartesian3.dot(offset, right));
      const vertical = Math.abs(Cesium.Cartesian3.dot(offset, up));
      requiredRange = Math.max(
        requiredRange,
        horizontal / horizontalLimit - forward,
        vertical / verticalLimit - forward
      );
    };
    const end = Math.min(lastIndex, positions.length - 1);
    for (let index = 0; index <= end; index += 1) include(positions[index]);
    if (currentPosition) include(currentPosition);

    return Cesium.Math.clamp(
      Math.max(0, requiredRange) * CAMERA_FIT_PADDING,
      CAMERA_MIN_RANGE_M,
      CAMERA_MAX_RANGE_M
    );
  }

  function fittedCameraView(target, heading, pitch, lastIndex = positions.length - 1, currentPosition = null) {
    const originalTarget = Cesium.Cartesian3.clone(target);
    let adjustedTarget = Cesium.Cartesian3.clone(target);
    const range = rangeForTarget(adjustedTarget, heading, pitch, lastIndex, currentPosition);
    // Move the aim point upward in camera space, which composes the route lower
    // in the frame and keeps it clear of the two landscape information cards.
    if (CAMERA_SCREEN_Y !== 0) {
      viewer.camera.lookAt(adjustedTarget, new Cesium.HeadingPitchRange(heading, pitch, range));
      const tanHalfVertical = Math.tan(viewer.camera.frustum.fovy * 0.5);
      const worldOffset = 2 * CAMERA_SCREEN_Y * range * tanHalfVertical;
      adjustedTarget = Cesium.Cartesian3.add(
        originalTarget,
        Cesium.Cartesian3.multiplyByScalar(viewer.camera.upWC, worldOffset, new Cesium.Cartesian3()),
        new Cesium.Cartesian3()
      );
    }
    return { target: adjustedTarget, range };
  }

  const overviewHeading = Cesium.Math.toRadians(setting("overview_heading_deg", 18));
  const overviewPitch = Cesium.Math.toRadians(setting("overview_pitch_deg", -45));
  const overviewView = AUTO_CAMERA_RANGE
    ? fittedCameraView(center, overviewHeading, overviewPitch)
    : null;
  const overviewRange = AUTO_CAMERA_RANGE
    ? overviewView.range
    : Math.max(
      setting("overview_min_range_m", 18000),
      diagonal * setting("overview_range_scale", 1.0)
    );

  function cameraHeadingAt(progress) {
    const value = Cesium.Math.clamp(progress, 0, 1);
    const eased = value * value * (3 - 2 * value);
    // One-way cinematic orbit: smooth at both ends and never reverses direction.
    // Over the 60-second render this is about 1.2 degrees per second.
    return Cesium.Math.toRadians(ORBIT_START_DEG + eased * ORBIT_DEGREES);
  }

  function setOverview(progress = 1) {
    const startScale = setting("overview_start_scale", 1.16);
    const endScale = setting("overview_end_scale", 1.0);
    const range = overviewRange * Cesium.Math.lerp(startScale, endScale, progress);
    viewer.camera.lookAt(AUTO_CAMERA_RANGE ? overviewView.target : center, new Cesium.HeadingPitchRange(
      overviewHeading,
      overviewPitch,
      range * (AUTO_CAMERA_RANGE ? 1 : setting("overview_distance_scale", 1.12))
    ));
    return range;
  }

  function setFinalOverview(progress) {
    const value = Cesium.Math.clamp(progress, 0, 1);
    const eased = value * value * (3 - 2 * value);
    const finalPosition = positions[positions.length - 1];
    const target = Cesium.Cartesian3.lerp(finalPosition, center, eased, new Cesium.Cartesian3());
    const heading = ORBIT_START_DEG + ORBIT_DEGREES
      + eased * setting("final_orbit_degrees", 180);
    const pitch = Cesium.Math.lerp(
      CAMERA_PITCH_DEG, setting("final_pitch_deg", -72), eased
    );
    const headingRadians = Cesium.Math.toRadians(heading);
    const pitchRadians = Cesium.Math.toRadians(pitch);
    const fittedView = AUTO_CAMERA_RANGE
      ? fittedCameraView(target, headingRadians, pitchRadians)
      : null;
    const range = AUTO_CAMERA_RANGE
      ? fittedView.range
      : Cesium.Math.lerp(
        CAMERA_RANGE_M,
        overviewRange * setting("final_range_scale", 1.18),
        eased
      );
    viewer.camera.lookAt(AUTO_CAMERA_RANGE ? fittedView.target : target, new Cesium.HeadingPitchRange(
      headingRadians, pitchRadians, range
    ));
    return range;
  }

  async function settleTerrain(maxFrames = 16) {
    for (let frame = 0; frame < maxFrames; frame += 1) {
      viewer.scene.requestRender();
      viewer.scene.render();
      await new Promise((resolve) => requestAnimationFrame(resolve));
      if (viewer.scene.globe.tilesLoaded && frame > 1) return;
    }
  }

  // Called by render_video.py. It is deterministic: frame N always produces the same image.
  window.renderFrame = async (frameNumber, totalFrames) => {
    const videoProgress = totalFrames <= 1 ? 1 : frameNumber / (totalFrames - 1);
    let trackProgress;
    const trackEnd = 1 - OUTRO_RATIO;
    const trackDuration = Math.max(0.001, trackEnd - INTRO_RATIO);
    if (videoProgress < INTRO_RATIO) trackProgress = 0;
    else if (videoProgress > trackEnd) trackProgress = 1;
    else trackProgress = (videoProgress - INTRO_RATIO) / trackDuration;
    trackProgress = Cesium.Math.clamp(trackProgress, 0, 1);
    const elapsed = trackProgress * metadata.duration_seconds;
    const sample = trackSampleAtTime(elapsed);
    const liveMetric = metricSampleAtTime(elapsed);
    runner.position = sample.position;

    let cameraRange;
    if (videoProgress < INTRO_RATIO) {
      cameraRange = setOverview(videoProgress / INTRO_RATIO);
    } else if (videoProgress > trackEnd) {
      cameraRange = setFinalOverview((videoProgress - trackEnd) / Math.max(0.001, OUTRO_RATIO));
    } else {
      const forwardPosition = positionAtDistance(sample.point[4] + CAMERA_LOOK_AHEAD_M);
      const target = Cesium.Cartesian3.lerp(sample.position, forwardPosition, CAMERA_TARGET_LEAD, new Cesium.Cartesian3());
      const heading = cameraHeadingAt(trackProgress);
      const pitch = Cesium.Math.toRadians(CAMERA_PITCH_DEG);
      const fittedView = AUTO_CAMERA_RANGE
        ? fittedCameraView(target, heading, pitch, sample.lowerIndex, sample.position)
        : null;
      cameraRange = AUTO_CAMERA_RANGE ? fittedView.range : CAMERA_RANGE_M;
      viewer.camera.lookAt(AUTO_CAMERA_RANGE ? fittedView.target : target, new Cesium.HeadingPitchRange(
        heading,
        pitch,
        cameraRange
      ));
    }
    window.__CAMERA_FIT__ = {
      auto: AUTO_CAMERA_RANGE,
      range: cameraRange,
      overviewRange,
      trackRadius: trackBounds.radius,
    };

    const distanceProgress = sample.point[4] / metadata.distance_m;
    const displayedDistance = distanceProgress * reportedDistance;
    $("distance").textContent = displayedDistance.toFixed(2);
    $("elapsed").textContent = formatDuration(elapsed);
    $("altitude").textContent = Math.round(sample.point[2]);
    $("heartRate").textContent = Number.isFinite(liveMetric.heartRate) ? Math.round(liveMetric.heartRate) : "--";
    $("pace").textContent = formatPace(liveMetric.speed);
    $("progressBar").style.width = `${trackProgress * 100}%`;
    $("titleCard").style.opacity = videoProgress < INTRO_RATIO ? "1" : "0";
    $("elevationPanel").style.opacity = videoProgress < INTRO_RATIO ? "0" : "1";
    $("liveMetrics").style.opacity = videoProgress < INTRO_RATIO ? "0" : "1";
    drawElevationProfile(distanceProgress, sample.point);
    await settleTerrain(1);
    drawRouteOverlay(sample.lowerIndex, sample.position);
    return { index: sample.lowerIndex, elapsed, trackProgress, distanceProgress };
  };

  setOverview(0);
  await window.renderFrame(0, 2);
  await settleTerrain(40);
  window.__TRACK_READY__ = true;
})().catch((error) => {
  document.getElementById("error").style.display = "block";
  document.getElementById("error").textContent = error.stack || String(error);
  window.__TRACK_ERROR__ = error.stack || String(error);
  console.error(error);
});
