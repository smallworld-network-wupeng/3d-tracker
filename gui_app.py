#!/usr/bin/env python3
"""Desktop interface for the 3D track movie generator."""

from __future__ import annotations

import re
import shutil
import json
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtCore import QDate, QDateTime, QLocale, QProcess, QRectF, QSettings, QSignalBlocker, QTime, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QKeySequence, QPainter
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSplitter,
    QStyle,
    QStyleOptionSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_config import (
    PROJECT_FILE_SUFFIX,
    SUPPORTED_MUSIC_SUFFIXES,
    SUPPORTED_TRACK_SUFFIXES,
    VIDEO_GROUP_WINDOW,
    Segment,
    build_editor_project,
    build_project_config,
    display_creation_time,
    format_timecode,
    list_video_files,
    normalize_creation_time,
    output_dimensions,
    parse_timecode,
    popup_safe_bounds,
    read_editor_project,
    safe_filename,
    write_editor_project,
    write_project_config,
)
from compose_media_video import group_segments, load_configured_segments
from photo_editor import PhotoEditorDialog
from photo_events import (
    PhotoEvent,
    activity_wall_time,
    list_photo_files,
)
from prepare_track import prepare
from runtime_paths import (
    IS_BUNDLED,
    RESOURCE_ROOT,
    WORK_ROOT,
    configure_runtime_environment,
    default_output_directory,
    render_worker_executable,
)


configure_runtime_environment()
ROOT = RESOURCE_ROOT
APP_NAMES = {
    "zh": "3D轨迹影片生成器",
    "en": "3D Track Movie Generator",
}


def system_language(locale_name: str | None = None) -> str:
    """Return the supported UI language for a Qt/system locale name."""

    if locale_name is None:
        system_locale = QLocale.system()
        ui_languages = system_locale.uiLanguages()
        name = ui_languages[0] if ui_languages else system_locale.name()
    else:
        name = locale_name
    return "zh" if name.lower().replace("-", "_").startswith("zh") else "en"


def ui_text(language: str, chinese: str, english: str) -> str:
    return chinese if language == "zh" else english


ERROR_TRANSLATIONS = {
    "影片文件名无效": "The video filename is invalid.",
    "起点不能小于 0": "The start time cannot be less than 0.",
    "终点必须晚于起点": "The end time must be later than the start time.",
    "请填写拍摄时间": "Enter the recording time.",
    "拍摄时间应写成 YYYY-MM-DD HH:MM:SS": "Use YYYY-MM-DD HH:MM:SS for the recording time.",
    "时间应写成 MM:SS 或 HH:MM:SS": "Use MM:SS or HH:MM:SS for the time.",
    "无法识别这个时间": "The time could not be parsed.",
    "时间不能小于 0": "The time cannot be less than 0.",
    "秒和分钟不能大于等于 60": "Seconds and minutes must be less than 60.",
    "请选择有效的 FIT 或 KML 轨迹文件": "Select a valid FIT or KML track file.",
    "请填写活动名称": "Enter an activity name.",
    "影片时长必须大于 0": "The movie duration must be greater than 0.",
    "不支持的画面方向或输出画质": "The selected orientation or output quality is not supported.",
}


def localized_error(language: str, error: Exception | str) -> str:
    message = str(error)
    if language == "zh":
        return message
    if message in ERROR_TRANSLATIONS:
        return ERROR_TRANSLATIONS[message]
    line_match = re.fullmatch(r"第 (\d+) 行格式错误", message)
    if line_match:
        return f"Line {line_match.group(1)} has an invalid format."
    return message


def probe_video_creation_time(path: Path) -> str | None:
    """Read the MP4/MOV container creation_time without changing the source file."""

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format_tags=creation_time,com.apple.quicktime.creationdate",
                "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        tags = json.loads(result.stdout).get("format", {}).get("tags", {})
        creation = tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time")
        return normalize_creation_time(creation) if creation else None
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError):
        return None


STYLE = """
QMainWindow, QDialog { background: #f4f5f4; }
QWidget { color: #20262d; font-size: 14px; }
QGroupBox {
  font-size: 17px; font-weight: 700; border: 1px solid #cbd0d4;
  border-radius: 6px; margin-top: 12px; padding: 15px 12px 10px 12px; background: #ffffff;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 7px; color: #222a31; }
QLineEdit, QComboBox, QAbstractSpinBox {
  min-height: 34px; border: 1px solid #bfc5ca; border-radius: 5px;
  padding: 0 9px; background: #fbfcfc; color: #20262d;
  selection-background-color: #f2b633; selection-color: #20262d;
}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {
  border: 1px solid #e7a91d; background: white;
}
QPushButton {
  min-height: 34px; padding: 0 15px; border: 1px solid #b9bfc4;
  border-radius: 5px; background: #f7f8f8;
}
QPushButton:hover { background: #ffffff; border-color: #8f979e; }
QPushButton:pressed { background: #e8ebed; }
QPushButton#openProjectButton, QPushButton#saveProjectButton {
  min-height: 44px; min-width: 130px; font-size: 17px; font-weight: 700;
}
QPushButton#primaryButton {
  min-height: 44px; min-width: 175px; font-size: 17px; font-weight: 700;
  background: #f5b82e; border-color: #e6a716;
}
QPushButton#primaryButton:hover { background: #ffc84a; }
QPushButton#choiceButton { min-width: 120px; }
QPushButton#choiceButton:checked { background: #f5bd3d; border-color: #e5a91e; font-weight: 700; }
QLabel#title { font-size: 28px; font-weight: 800; }
QLabel#subtitle { color: #69727a; font-size: 14px; }
QLabel#success { color: #2f8b3a; font-weight: 650; }
QLabel#summary { background: #f0f7e8; border-radius: 5px; padding: 8px 11px; }
QTableWidget, QListWidget, QPlainTextEdit {
  border: 1px solid #c5cbd0; background: white; alternate-background-color: #f5f7f8;
}
QHeaderView::section { background: #edf0f2; padding: 7px; border: none; border-right: 1px solid #d5dade; }
QCalendarWidget { background: #ffffff; color: #20262d; }
QCalendarWidget QWidget#qt_calendar_navigationbar {
  background: #edf0f2; border-bottom: 1px solid #d5dade;
}
QCalendarWidget QToolButton {
  color: #20262d; background: transparent; border: none; font-weight: 700;
}
QCalendarWidget QToolButton:hover { background: #ffffff; }
QCalendarWidget QMenu { background: #ffffff; color: #20262d; }
QCalendarWidget QSpinBox {
  background: #ffffff; color: #20262d; selection-background-color: #f2b633;
}
QCalendarWidget QAbstractItemView:enabled {
  background: #ffffff; color: #20262d; alternate-background-color: #ffffff;
  selection-background-color: #f5b82e; selection-color: #20262d; outline: none;
}
QCalendarWidget QAbstractItemView:disabled { color: #9aa1a7; }
QProgressBar { border: 1px solid #c1c7cc; border-radius: 5px; text-align: center; background: white; }
QProgressBar::chunk { background: #f2b633; border-radius: 4px; }
"""


class ChoiceButtons(QWidget):
    def __init__(self, choices: list[tuple[str, str]], selected: str, parent=None):
        super().__init__(parent)
        self.group = QButtonGroup(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for text, value in choices:
            button = QPushButton(text)
            button.setObjectName("choiceButton")
            button.setCheckable(True)
            button.setProperty("choiceValue", value)
            self.group.addButton(button)
            layout.addWidget(button)
            if value == selected:
                button.setChecked(True)

    def value(self) -> str:
        button = self.group.checkedButton()
        return str(button.property("choiceValue"))

    def set_value(self, value: str) -> None:
        for button in self.group.buttons():
            button.setChecked(str(button.property("choiceValue")) == value)


class OptionalDateTimeEdit(QDateTimeEdit):
    """A calendar-backed date/time picker with a genuine unselected state."""

    def __init__(self, parent=None, *, language: str = "zh"):
        super().__init__(parent)
        self.empty_value = QDateTime(QDate(1900, 1, 1), QTime(0, 0, 0))
        self.setMinimumDateTime(self.empty_value)
        self.setSpecialValueText(ui_text(
            language,
            "\u8bf7\u9009\u62e9\u62cd\u6444\u65e5\u671f\u548c\u65f6\u95f4",
            "Select the recording date and time",
        ))
        self.setDateTime(self.empty_value)
        self.setCalendarPopup(True)

    def clear_value(self) -> None:
        blocker = QSignalBlocker(self)
        self.setDateTime(self.empty_value)
        del blocker

    def mousePressEvent(self, event) -> None:
        was_empty = self.dateTime() == self.empty_value
        super().mousePressEvent(event)
        if was_empty:
            QTimer.singleShot(0, self._show_current_month)

    def _show_current_month(self) -> None:
        if self.calendarWidget():
            today = QDate.currentDate()
            self.calendarWidget().setCurrentPage(today.year(), today.month())


class SegmentTimelineSlider(QSlider):
    """A seek slider that highlights the selected video intervals."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._segment_ranges: list[tuple[int, int]] = []
        self._draft_start: int | None = None
        self._draft_end: int | None = None
        self._follow_playhead = False

    def set_draft_range(
        self, start: int | None = None, end: int | None = None, *, follow_playhead: bool = False
    ) -> None:
        self._draft_start = start
        self._draft_end = end
        self._follow_playhead = follow_playhead
        self.update()

    def set_segment_ranges(self, ranges: list[tuple[int, int]]) -> None:
        normalized = sorted(
            (min(start, end), max(start, end))
            for start, end in ranges
            if start != end
        )
        if normalized == self._segment_ranges:
            return
        self._segment_ranges = normalized
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.maximum() <= self.minimum() or (
            not self._segment_ranges and self._draft_start is None
        ):
            return

        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.CC_Slider,
            option,
            QStyle.SC_SliderGroove,
            self,
        )
        handle = self.style().subControlRect(
            QStyle.CC_Slider,
            option,
            QStyle.SC_SliderHandle,
            self,
        )
        if groove.isEmpty() or handle.isEmpty():
            return

        # Map each timestamp to the center of the handle at that slider value,
        # so highlights line up with the seek position at both endpoints.
        slider_min = groove.left()
        slider_span = max(0, groove.width() - handle.width())
        handle_radius = handle.width() / 2
        marker_height = max(5, min(7, groove.height()))
        marker_top = groove.center().y() - marker_height / 2

        def timeline_x(value: int) -> float:
            value = max(self.minimum(), min(value, self.maximum()))
            return slider_min + handle_radius + QStyle.sliderPositionFromValue(
                self.minimum(), self.maximum(), value, slider_span, option.upsideDown
            )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        def draw_range(start: int, end: int) -> None:
            if end <= start or end <= self.minimum() or start >= self.maximum():
                return
            left, right = sorted((timeline_x(start), timeline_x(end)))
            bounds = QRectF(left, marker_top, max(1.0, right - left), marker_height)
            painter.drawRoundedRect(bounds, 2.5, 2.5)

        painter.save()
        painter.setBrush(QColor("#ef4444"))
        painter.setClipRect(groove.adjusted(0, -3, 0, 3))
        for start, end in self._segment_ranges:
            draw_range(start, end)
        draft_end = self.sliderPosition() if self._follow_playhead else self._draft_end
        if self._draft_start is not None and draft_end is not None:
            painter.setBrush(QColor("#dc2626"))
            draw_range(self._draft_start, draft_end)
        painter.restore()

        # Keep the tops of the endpoint marks visible above the seek handle.
        painter.setBrush(QColor("#dc2626"))
        flag_top = max(1, min(handle.top(), marker_top) - 6)
        for endpoint in (self._draft_start, self._draft_end):
            if endpoint is not None:
                x = timeline_x(endpoint)
                painter.drawRect(QRectF(x - 1, flag_top, 2, marker_top + 2 - flag_top))
                painter.drawRoundedRect(QRectF(x - 3, flag_top, 6, 4), 1, 1)

        # The markers are drawn over the groove; redraw the handle so it always
        # remains visible and easy to drag when it sits inside a selected range.
        painter.setRenderHint(QPainter.Antialiasing, False)
        option.subControls = QStyle.SC_SliderHandle
        self.style().drawComplexControl(QStyle.CC_Slider, option, painter, self)
        painter.end()


class ClipEditorDialog(QDialog):
    def __init__(
        self, media_directory: Path, segments: list[Segment], parent=None, *, language: str = "zh"
    ):
        super().__init__(parent)
        self.language = language
        self.setWindowTitle(self.t(
            f"编辑影片片段 - {APP_NAMES['zh']}",
            f"Edit Video Clips - {APP_NAMES['en']}",
        ))
        self.resize(1120, 760)
        self.media_directory = media_directory
        self.segments = list(segments)
        self.video_files = list_video_files(media_directory)
        self.current_file: Path | None = None
        self.preview_end_ms: int | None = None
        self.metadata_creation_times: dict[str, str | None] = {}
        self.creation_time_available = False

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.8)

        root = QVBoxLayout(self)
        intro = QLabel(
            self.t(
                "选择影片，修正影片开始拍摄时间，再定位起点和终点；"
                "同一影片可以添加多个片段。",
                "Choose a video, correct its recording start time, then mark the start "
                "and end points. You can add multiple clips from one video.",
            )
        )
        intro.setStyleSheet("color:#5f6870; padding:3px 0 7px 0;")
        root.addWidget(intro)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 5, 0)
        left_layout.addWidget(QLabel(self.t(
            f"影片列表（{len(self.video_files)}）",
            f"Videos ({len(self.video_files)})",
        )))
        self.file_list = QListWidget()
        left_layout.addWidget(self.file_list, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(5, 0, 0, 0)
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(290)
        self.video_widget.setStyleSheet("background:#111; border:1px solid #30363a;")
        self.player.setVideoOutput(self.video_widget)
        right_layout.addWidget(self.video_widget, 3)

        creation_row = QHBoxLayout()
        self.creation_time_edit = OptionalDateTimeEdit(language=self.language)
        self.creation_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.creation_time_edit.setCalendarPopup(True)
        self.creation_time_edit.setKeyboardTracking(False)
        self.creation_time_edit.lineEdit().setPlaceholderText(self.t(
            "请选择拍摄日期和时间", "Select the recording date and time"
        ))
        self.creation_time_edit.setToolTip(
            self.t(
                "选择原始影片第 0 秒的本地拍摄日期和时间",
                "Select the local date and time at second 0 of the source video",
            )
        )
        self.apply_creation_time_button = QPushButton(self.t(
            "应用到当前影片", "Apply to Current Video"
        ))
        self.creation_time_edit.dateTimeChanged.connect(self._creation_time_changed)
        creation_row.addWidget(QLabel(self.t(
            "拍摄时间（creation_time）", "Recording time (creation_time)"
        )))
        creation_row.addWidget(self.creation_time_edit, 1)
        creation_row.addWidget(self.apply_creation_time_button)
        right_layout.addLayout(creation_row)
        self.creation_time_status = QLabel("")
        self.creation_time_status.setStyleSheet("color:#68727a; padding-bottom:3px;")
        right_layout.addWidget(self.creation_time_status)

        controls = QHBoxLayout()
        self.play_button = QPushButton(self.t("播放", "Play"))
        self.position_label = QLabel("00:00:00.000 / 00:00:00.000")
        self.seek = SegmentTimelineSlider(Qt.Horizontal)
        self.seek.setMinimumHeight(32)
        self.seek.setRange(0, 0)
        self.seek.setToolTip(self.t(
            "红色区域表示正在标记或已添加的片段",
            "Red areas show the clip being marked or clips already added",
        ))
        controls.addWidget(self.play_button)
        controls.addWidget(self.seek, 1)
        controls.addWidget(self.position_label)
        right_layout.addLayout(controls)

        mark_row = QHBoxLayout()
        self.start_edit = QLineEdit("00:00:00.000")
        self.end_edit = QLineEdit("00:00:00.000")
        self.mark_start = QPushButton(self.t("当前位置设为起点", "Set Current Position as Start"))
        self.mark_end = QPushButton(self.t("当前位置设为终点", "Set Current Position as End"))
        self.add_segment = QPushButton(self.t("添加片段", "Add Clip"))
        mark_row.addWidget(QLabel(self.t("起点", "Start")))
        mark_row.addWidget(self.start_edit)
        mark_row.addWidget(self.mark_start)
        mark_row.addSpacing(8)
        mark_row.addWidget(QLabel(self.t("终点", "End")))
        mark_row.addWidget(self.end_edit)
        mark_row.addWidget(self.mark_end)
        mark_row.addWidget(self.add_segment)
        right_layout.addLayout(mark_row)

        self.segment_table = QTableWidget(0, 5)
        self.segment_table.setHorizontalHeaderLabels(
            [
                self.t("影片拍摄时间", "Recording Time"),
                self.t("起点", "Start"),
                self.t("终点", "End"),
                self.t("时长", "Duration"),
                self.t("操作", "Action"),
            ]
        )
        self.segment_table.setAlternatingRowColors(True)
        self.segment_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.segment_table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.segment_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        right_layout.addWidget(QLabel(self.t("当前影片的剪辑片段", "Clips from Current Video")))
        right_layout.addWidget(self.segment_table, 2)
        splitter.addWidget(right)
        splitter.setSizes([270, 760])

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(self.t("保存片段", "Save Clips"))
        buttons.button(QDialogButtonBox.Cancel).setText(self.t("取消", "Cancel"))
        root.addWidget(buttons)

        self._populate_files()
        self.file_list.currentRowChanged.connect(self._select_file)
        self.play_button.clicked.connect(self._toggle_playback)
        self.seek.actionTriggered.connect(self._seek_to_slider_position)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._playback_state_changed)
        self.mark_start.clicked.connect(self._mark_segment_start)
        self.mark_end.clicked.connect(self._mark_segment_end)
        self.start_edit.textEdited.connect(self._update_draft_range)
        self.end_edit.textEdited.connect(self._update_draft_range)
        self.add_segment.clicked.connect(self._add_segment)
        self.apply_creation_time_button.clicked.connect(self._apply_creation_time)
        self.segment_table.cellDoubleClicked.connect(self._play_segment)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        if self.video_files:
            self.file_list.setCurrentRow(0)

    def t(self, chinese: str, english: str) -> str:
        return ui_text(self.language, chinese, english)

    def error_text(self, error: Exception | str) -> str:
        return localized_error(self.language, error)

    def _populate_files(self) -> None:
        counts = Counter(segment.file for segment in self.segments)
        for row, path in enumerate(self.video_files):
            suffix = (
                self.t(
                    f"  ·  {counts[path.name]} 个片段",
                    f"  ·  {counts[path.name]} clips",
                )
                if counts[path.name] else ""
            )
            item = self.file_list.item(row)
            if item is None:
                item = QListWidgetItem()
                item.setData(Qt.UserRole, str(path))
                self.file_list.addItem(item)
            item.setText(path.name + suffix)

    def _select_file(self, row: int) -> None:
        if row < 0:
            return
        item = self.file_list.item(row)
        self.current_file = Path(item.data(Qt.UserRole))
        self.seek.setRange(0, 0)
        self.seek.set_draft_range()
        self.preview_end_ms = None
        self.start_edit.setText("00:00:00.000")
        self.end_edit.setText("00:00:00.000")
        self.player.setSource(QUrl.fromLocalFile(str(self.current_file)))
        overrides = {
            segment.creation_time
            for segment in self.segments
            if segment.file == self.current_file.name and segment.creation_time
        }
        if overrides:
            value = sorted(overrides)[0]
            self._set_creation_time(value)
            self.creation_time_status.setText(self.t(
                "使用已保存的拍摄时间覆盖值。",
                "Using the saved recording-time override.",
            ))
        else:
            filename = self.current_file.name
            if filename not in self.metadata_creation_times:
                self.metadata_creation_times[filename] = probe_video_creation_time(self.current_file)
            value = self.metadata_creation_times[filename]
            if value:
                self._set_creation_time(value)
            else:
                self.creation_time_edit.clear_value()
                self.creation_time_available = False
            self.creation_time_status.setText(
                self.t(
                "已从影片元数据读取，可以在这里修正。",
                "Read from the video metadata; you can correct it here.",
                )
                if value else
                self.t(
                "该影片没有 creation_time，请选择实际开始拍摄时间。",
                "This video has no creation_time. Select its actual recording start time.",
                )
            )
        self._refresh_segments()

    def _set_creation_time(self, value: str) -> None:
        date_time = QDateTime.fromString(display_creation_time(value), "yyyy-MM-dd HH:mm:ss")
        if not date_time.isValid():
            raise ValueError(self.t("无法识别拍摄时间", "The recording time could not be parsed."))
        blocker = QSignalBlocker(self.creation_time_edit)
        self.creation_time_edit.setDateTime(date_time)
        del blocker
        self.creation_time_available = True

    def _creation_time_changed(self, _value: QDateTime) -> None:
        self.creation_time_available = True

    def _validated_creation_time(self) -> str:
        if not self.current_file:
            raise ValueError(self.t("请先选择影片", "Select a video first."))
        if not self.creation_time_available:
            raise ValueError(self.t(
                "该影片没有可用的 creation_time，请选择拍摄时间",
                "This video has no usable creation_time. Select its recording time.",
            ))
        return normalize_creation_time(
            self.creation_time_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        )

    def _apply_creation_time(self) -> bool:
        if not self.current_file:
            return False
        try:
            value = self._validated_creation_time()
        except ValueError as error:
            QMessageBox.warning(
                self,
                self.t("无法保存拍摄时间", "Could Not Save Recording Time"),
                self.error_text(error),
            )
            return False
        filename = self.current_file.name
        self.segments = [
            replace(segment, creation_time=value) if segment.file == filename else segment
            for segment in self.segments
        ]
        self._set_creation_time(value)
        self.creation_time_status.setText(self.t(
            "已将修正后的拍摄时间应用到当前影片的所有片段。",
            "The corrected recording time was applied to all clips from this video.",
        ))
        self._refresh_segments()
        return True

    def _toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.preview_end_ms = None
            self.player.play()

    def _seek_to_slider_position(self, _action: int) -> None:
        self.player.setPosition(self.seek.sliderPosition())

    def _position_changed(self, position: int) -> None:
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        self.position_label.setText(
            f"{format_timecode(position / 1000)} / {format_timecode(self.player.duration() / 1000)}"
        )
        if self.preview_end_ms is not None and position >= self.preview_end_ms:
            self.preview_end_ms = None
            self.player.pause()

    def _duration_changed(self, duration: int) -> None:
        self.seek.setRange(0, duration)
        self.position_label.setText(f"00:00:00.000 / {format_timecode(duration / 1000)}")
        if self.end_edit.text() == "00:00:00.000" and duration > 0:
            self.end_edit.setText(format_timecode(duration / 1000))

    def _playback_state_changed(self, state) -> None:
        self.play_button.setText(
            self.t("暂停", "Pause")
            if state == QMediaPlayer.PlayingState else self.t("播放", "Play")
        )

    def _mark_segment_start(self) -> None:
        if self.seek.maximum() <= 0:
            return
        self.start_edit.setText(format_timecode(self.seek.sliderPosition() / 1000))
        self.end_edit.clear()
        self._update_draft_range()

    def _mark_segment_end(self) -> None:
        if self.seek.maximum() <= 0:
            return
        position = self.seek.sliderPosition() / 1000
        try:
            if position <= parse_timecode(self.start_edit.text()):
                raise ValueError(self.t("终点必须晚于起点", "The end time must be later than the start time."))
        except ValueError as error:
            QMessageBox.warning(
                self,
                self.t("无法设置终点", "Could Not Set End Time"),
                self.error_text(error),
            )
            return
        self.end_edit.setText(format_timecode(position))
        self._update_draft_range()

    def _update_draft_range(self) -> None:
        end_text = self.end_edit.text().strip()
        try:
            start = round(parse_timecode(self.start_edit.text()) * 1000)
        except (ValueError, OverflowError):
            self.seek.set_draft_range()
            return
        if not end_text:
            self.seek.set_draft_range(start, follow_playhead=True)
            return
        try:
            end = round(parse_timecode(end_text) * 1000)
        except (ValueError, OverflowError):
            end = start
        self.seek.set_draft_range(start, end if end > start else None)

    def _add_segment(self) -> None:
        if not self.current_file:
            return
        try:
            creation_time = self._validated_creation_time()
            if not self.end_edit.text().strip():
                raise ValueError(self.t("请先设置片段终点", "Set the clip end time first."))
            segment = Segment(
                self.current_file.name,
                parse_timecode(self.start_edit.text()),
                parse_timecode(self.end_edit.text()),
                creation_time,
            )
            segment.validate()
            duration = self.player.duration() / 1000
            if duration > 0 and segment.end > duration + 0.05:
                raise ValueError(self.t(
                    "终点超过了影片总时长", "The end time is beyond the video duration."
                ))
        except ValueError as error:
            QMessageBox.warning(
                self,
                self.t("无法添加片段", "Could Not Add Clip"),
                self.error_text(error),
            )
            return
        self.segments = [
            replace(value, creation_time=creation_time)
            if value.file == self.current_file.name else value
            for value in self.segments
        ]
        self.segments.append(segment)
        self.segments.sort(key=lambda item: (item.file.casefold(), item.start, item.end))
        self.seek.set_draft_range()
        self.start_edit.setText("00:00:00.000")
        self.end_edit.setText(format_timecode(self.player.duration() / 1000))
        self._populate_files()
        self._refresh_segments()

    def _refresh_segments(self) -> None:
        filename = self.current_file.name if self.current_file else ""
        values = [segment for segment in self.segments if segment.file == filename]
        self.seek.set_segment_ranges([
            (round(segment.start * 1000), round(segment.end * 1000))
            for segment in values
        ])
        self.segment_table.setRowCount(len(values))
        for row, segment in enumerate(values):
            creation_time = (
                display_creation_time(segment.creation_time)
                if segment.creation_time else self.t("使用影片元数据", "Use video metadata")
            )
            self.segment_table.setItem(row, 0, QTableWidgetItem(creation_time))
            self.segment_table.setItem(row, 1, QTableWidgetItem(format_timecode(segment.start)))
            self.segment_table.setItem(row, 2, QTableWidgetItem(format_timecode(segment.end)))
            self.segment_table.setItem(
                row, 3, QTableWidgetItem(self.t(
                    f"{segment.duration:.1f} 秒", f"{segment.duration:.1f} sec"
                ))
            )
            button = QPushButton(self.t("删除", "Delete"))
            button.clicked.connect(lambda _checked=False, value=segment: self._delete_segment(value))
            self.segment_table.setCellWidget(row, 4, button)

    def _delete_segment(self, segment: Segment) -> None:
        self.segments.remove(segment)
        self._populate_files()
        self._refresh_segments()

    def _play_segment(self, row: int, _column: int) -> None:
        filename = self.current_file.name if self.current_file else ""
        values = [segment for segment in self.segments if segment.file == filename]
        if row >= len(values):
            return
        segment = values[row]
        self.player.setPosition(round(segment.start * 1000))
        self.preview_end_ms = round(segment.end * 1000)
        self.player.play()

    def accept(self) -> None:
        filename = self.current_file.name if self.current_file else ""
        if any(segment.file == filename for segment in self.segments):
            if not self._apply_creation_time():
                return
        missing_times = []
        for filename in sorted({segment.file for segment in self.segments}):
            overrides = {
                segment.creation_time
                for segment in self.segments
                if segment.file == filename and segment.creation_time
            }
            if len(overrides) > 1:
                QMessageBox.warning(
                    self,
                    self.t("拍摄时间不一致", "Recording Times Do Not Match"),
                    self.t(
                        f"{filename} 的多个片段使用了不同的拍摄时间，请重新应用一个时间。",
                        f"Clips from {filename} use different recording times. Apply one time again.",
                    ),
                )
                return
            if overrides:
                value = next(iter(overrides))
                self.segments = [
                    replace(segment, creation_time=value) if segment.file == filename else segment
                    for segment in self.segments
                ]
                continue
            if filename not in self.metadata_creation_times:
                self.metadata_creation_times[filename] = probe_video_creation_time(
                    self.media_directory / filename
                )
            if not self.metadata_creation_times[filename]:
                missing_times.append(filename)
        if missing_times:
            QMessageBox.warning(
                self,
                self.t("还有影片缺少拍摄时间", "Videos Are Missing Recording Times"),
                self.t(
                "请依次选择以下影片，填写拍摄时间并点击“应用到当前影片”：\n\n",
                "Select each video below, enter its recording time, and click "
                '"Apply to Current Video":\n\n',
                )
                + "\n".join(missing_times),
            )
            return
        super().accept()

    def closeEvent(self, event) -> None:
        self.player.stop()
        super().closeEvent(event)


class RenderDialog(QDialog):
    def __init__(self, title: str, parent=None, *, language: str = "zh"):
        super().__init__(parent)
        self.language = language
        self.setWindowTitle(title)
        self.resize(700, 430)
        layout = QVBoxLayout(self)
        self.status = QLabel(ui_text(language, "正在准备……", "Preparing…"))
        self.status.setFont(QFont(self.font().family(), 15, QFont.DemiBold))
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        self.cancel_button = QPushButton(ui_text(language, "取消", "Cancel"))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.cancel_button)
        layout.addLayout(row)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.language = system_language()
        self.setWindowTitle(APP_NAMES[self.language])
        self.resize(1080, 760)
        self.settings = QSettings("OpenAI-Codex", "3DTrackMovieGenerator")
        self.segments: list[Segment] = []
        self.photo_events: list[PhotoEvent] = []
        self.project_path: Path | None = None
        self.process: QProcess | None = None
        self.progress_dialog: RenderDialog | None = None
        self.expected_output: Path | None = None
        self.is_preview = False

        self._build_ui()
        self._build_menu()
        self._restore_settings()
        self._update_summary()

    def t(self, chinese: str, english: str) -> str:
        return ui_text(self.language, chinese, english)

    def error_text(self, error: Exception | str) -> str:
        return localized_error(self.language, error)

    def _capture_form(self) -> dict[str, str | float]:
        return {
            "track": self.track_edit.text(),
            "name": self.name_edit.text(),
            "orientation": self.orientation.value(),
            "duration": self.duration_combo.currentText(),
            "quality": self.quality.value(),
            "media": self.media_edit.text(),
            "photos": self.photos_edit.text(),
            "music": self.music_edit.text(),
            "music_start_offset": self.music_start_offset.value(),
            "output": self.output_edit.text(),
        }

    def _toggle_language(self) -> None:
        state = self._capture_form()
        self.language = "en" if self.language == "zh" else "zh"
        app_name = APP_NAMES[self.language]
        self.setWindowTitle(
            f"{app_name} — {self.project_path.stem}" if self.project_path else app_name
        )
        QApplication.instance().setApplicationName(app_name)
        old_central = self.takeCentralWidget()
        if old_central:
            old_central.deleteLater()
        self.menuBar().clear()
        self._build_ui()
        self._build_menu()
        self.track_edit.setText(state["track"])
        self.name_edit.setText(state["name"])
        self.orientation.set_value(state["orientation"])
        duration_match = re.search(r"\d+(?:\.\d+)?", state["duration"])
        if duration_match:
            seconds = duration_match.group()
            self.duration_combo.setCurrentText(self.t(f"{seconds}秒", f"{seconds} sec"))
        self.quality.set_value(state["quality"])
        self.media_edit.setText(state["media"])
        self.photos_edit.setText(state["photos"])
        self.music_edit.setText(state["music"])
        self.music_start_offset.setValue(float(state["music_start_offset"]))
        self.output_edit.setText(state["output"])
        self._update_summary()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(self.t("文件", "File"))
        clear_action = QAction(self.t("新建", "New"), self)
        clear_action.setShortcut(QKeySequence.StandardKey.New)
        clear_action.triggered.connect(self._clear_form)
        file_menu.addAction(clear_action)
        open_action = QAction(self.t("打开项目…", "Open Project…"), self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        save_action = QAction(self.t("保存项目", "Save Project"), self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)
        save_as_action = QAction(self.t("项目另存为…", "Save Project As…"), self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(lambda: self._save_project(save_as=True))
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        exit_action = QAction(self.t("退出", "Exit"), self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        help_menu = self.menuBar().addMenu(self.t("帮助", "Help"))
        about_action = QAction(self.t("关于", "About"), self)
        about_action.triggered.connect(
            lambda: QMessageBox.about(
                self,
                self.t(
                    f"关于 {APP_NAMES['zh']}",
                    f"About {APP_NAMES['en']}",
                ),
                self.t(
                    "导入 FIT/KML 轨迹、实拍片段、照片和背景音乐，生成 3D 轨迹影片。",
                    "Import a FIT/KML track, video clips, photos, and background music to create a 3D track movie.",
                ),
            )
        )
        help_menu.addAction(about_action)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 16, 24, 18)
        root.setSpacing(9)

        header = QHBoxLayout()
        icon = QLabel("⌁")
        icon.setStyleSheet("color:#eeaa1f; font-size:42px; font-weight:900;")
        titles = QVBoxLayout()
        title = QLabel(APP_NAMES[self.language])
        title.setObjectName("title")
        subtitle = QLabel(self.t(
            "导入素材，轻松生成你的3D轨迹影片",
            "Import your media and easily create a 3D track movie",
        ))
        subtitle.setObjectName("subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addWidget(icon)
        header.addLayout(titles)
        header.addStretch()
        language_button = QPushButton(self.t("English", "中文"))
        language_button.setToolTip(self.t(
            "切换到英文", "Switch to Chinese"
        ))
        language_button.clicked.connect(self._toggle_language)
        header.addWidget(language_button)
        root.addLayout(header)

        activity_box = QGroupBox(self.t("活动信息", "Activity"))
        activity = QGridLayout(activity_box)
        activity.setColumnStretch(1, 1)
        self.track_edit = QLineEdit()
        track_button = QPushButton(self.t("选择文件", "Choose File"))
        track_button.clicked.connect(self._choose_track)
        self.name_edit = QLineEdit()
        activity.addWidget(QLabel(self.t("轨迹文件", "Track File")), 0, 0)
        activity.addWidget(self.track_edit, 0, 1)
        activity.addWidget(track_button, 0, 2)
        activity.addWidget(QLabel(self.t("活动名称", "Activity Name")), 1, 0)
        activity.addWidget(self.name_edit, 1, 1, 1, 2)
        root.addWidget(activity_box)

        settings_box = QGroupBox(self.t("影片设置", "Movie Settings"))
        settings = QGridLayout(settings_box)
        settings.setColumnStretch(3, 1)
        self.orientation = ChoiceButtons(
            [
                (self.t("▭  横屏", "▭  Landscape"), "landscape"),
                (self.t("▯  竖屏", "▯  Portrait"), "portrait"),
            ],
            "landscape",
        )
        self.duration_combo = QComboBox()
        self.duration_combo.setEditable(True)
        self.duration_combo.addItems([
            self.t(f"{seconds}秒", f"{seconds} sec")
            for seconds in (15, 30, 45, 60, 90)
        ])
        self.duration_combo.setCurrentText(self.t("30秒", "30 sec"))
        self.quality = ChoiceButtons([("720P", "720p"), ("1080P", "1080p")], "1080p")
        settings.addWidget(QLabel(self.t("画面方向", "Orientation")), 0, 0)
        settings.addWidget(self.orientation, 0, 1)
        settings.addWidget(QLabel(self.t("影片时长", "Duration")), 0, 2)
        settings.addWidget(self.duration_combo, 0, 3)
        settings.addWidget(QLabel(self.t("输出画质", "Output Quality")), 0, 4)
        settings.addWidget(self.quality, 0, 5)
        root.addWidget(settings_box)

        media_box = QGroupBox(self.t("素材", "Media"))
        media = QGridLayout(media_box)
        media.setColumnStretch(1, 1)
        self.media_edit = QLineEdit()
        media_button = QPushButton(self.t("选择文件夹", "Choose Folder"))
        media_button.clicked.connect(self._choose_media_directory)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("summary")
        self.edit_segments_button = QPushButton(self.t("编辑影片片段", "Edit Video Clips"))
        self.edit_segments_button.clicked.connect(self._edit_segments)
        self.photos_edit = QLineEdit()
        self.photos_edit.setClearButtonEnabled(True)
        self.photos_edit.textChanged.connect(self._update_photo_summary)
        photos_button = QPushButton(self.t("选择文件夹", "Choose Folder"))
        photos_button.clicked.connect(self._choose_photo_directory)
        self.photo_summary = QLabel()
        self.photo_summary.setObjectName("summary")
        self.edit_photos_button = QPushButton(self.t("编辑照片", "Edit Photos"))
        self.edit_photos_button.clicked.connect(self._edit_photos)
        self.music_edit = QLineEdit()
        music_button = QPushButton(self.t("选择音乐", "Choose Music"))
        music_button.clicked.connect(self._choose_music)
        self.music_start_offset = QDoubleSpinBox()
        self.music_start_offset.setRange(0.0, 86400.0)
        self.music_start_offset.setDecimals(1)
        self.music_start_offset.setSingleStep(0.5)
        self.music_start_offset.setSuffix(self.t(" 秒", " sec"))
        self.music_start_offset.setToolTip(self.t(
            "背景音乐在影片开始后多少秒开始播放",
            "How many seconds after the movie starts the background music should begin",
        ))
        media.addWidget(QLabel(self.t("影片文件夹", "Video Folder")), 0, 0)
        media.addWidget(self.media_edit, 0, 1)
        media.addWidget(media_button, 0, 2)
        media.addWidget(self.edit_segments_button, 0, 3)
        media.addWidget(QLabel(self.t("照片文件夹", "Photo Folder")), 1, 0)
        media.addWidget(self.photos_edit, 1, 1)
        media.addWidget(photos_button, 1, 2)
        media.addWidget(self.edit_photos_button, 1, 3)
        media.addWidget(QLabel(self.t("背景音乐", "Background Music")), 2, 0)
        media.addWidget(self.music_edit, 2, 1)
        media.addWidget(music_button, 2, 2)
        media.addWidget(QLabel(self.t("开始偏移", "Start Offset")), 2, 3)
        media.addWidget(self.music_start_offset, 2, 4)
        summaries = QHBoxLayout()
        summaries.addWidget(self.summary_label, 1)
        summaries.addWidget(self.photo_summary, 1)
        media.addLayout(summaries, 3, 1, 1, 3)
        root.addWidget(media_box)

        output_box = QGroupBox(self.t("输出", "Output"))
        output = QGridLayout(output_box)
        output.setColumnStretch(1, 1)
        self.output_edit = QLineEdit()
        output_button = QPushButton(self.t("选择位置", "Choose Location"))
        output_button.clicked.connect(self._choose_output_directory)
        output.addWidget(QLabel(self.t("保存到", "Save To")), 0, 0)
        output.addWidget(self.output_edit, 0, 1)
        output.addWidget(output_button, 0, 2)
        root.addWidget(output_box)
        root.addStretch()

        footer = QHBoxLayout()
        self.status_label = QLabel(self.t("●  请选择轨迹文件", "●  Select a track file"))
        self.status_label.setObjectName("success")
        self.open_project_button = QPushButton(self.t("打开项目…", "Open Project…"))
        self.open_project_button.setObjectName("openProjectButton")
        self.open_project_button.setToolTip(self.t(
            "打开已保存的 .3dtrack 项目文件",
            "Open a saved .3dtrack project file",
        ))
        self.open_project_button.clicked.connect(self._open_project)
        self.save_project_button = QPushButton(self.t("保存项目", "Save Project"))
        self.save_project_button.setObjectName("saveProjectButton")
        self.save_project_button.clicked.connect(self._save_project)
        generate_button = QPushButton(self.t("生成影片", "Generate Movie"))
        generate_button.setObjectName("primaryButton")
        generate_button.clicked.connect(lambda: self._start_render(preview=False))
        footer.addWidget(self.status_label)
        footer.addStretch()
        footer.addWidget(self.open_project_button)
        footer.addWidget(self.save_project_button)
        footer.addWidget(generate_button)
        root.addLayout(footer)

    def _last_directory(self, key: str, fallback: str = "") -> str:
        return str(self.settings.value(key, fallback))

    def _project_document(self, path: Path) -> dict:
        def optional_path(value: str) -> Path | None:
            return Path(value.strip()).expanduser() if value.strip() else None

        return build_editor_project(
            project_path=path,
            track_file=optional_path(self.track_edit.text()),
            activity_name=self.name_edit.text(),
            orientation=self.orientation.value(),
            quality=self.quality.value(),
            seconds=self._duration(),
            output_directory=optional_path(self.output_edit.text()),
            media_directory=optional_path(self.media_edit.text()),
            segments=self.segments,
            photo_directory=optional_path(self.photos_edit.text()),
            photo_events=[asdict(event) for event in self.photo_events],
            music_file=optional_path(self.music_edit.text()),
            music_start_offset_seconds=self.music_start_offset.value(),
        )

    def _save_project(self, _checked: bool = False, *, save_as: bool = False) -> bool:
        path = None if save_as else self.project_path
        if path is None:
            default_directory = self.output_edit.text().strip() or self._last_directory(
                "projectDirectory", str(default_output_directory())
            )
            default_name = safe_filename(self.name_edit.text()) + PROJECT_FILE_SUFFIX
            filename, _ = QFileDialog.getSaveFileName(
                self,
                self.t("保存项目", "Save Project"),
                str(Path(default_directory) / default_name),
                self.t("3D 轨迹项目 (*.3dtrack)", "3D Track projects (*.3dtrack)"),
            )
            if not filename:
                return False
            path = Path(filename)
            if path.suffix.lower() != PROJECT_FILE_SUFFIX:
                path = path.with_suffix(PROJECT_FILE_SUFFIX)
        try:
            write_editor_project(path, self._project_document(path))
        except (OSError, ValueError) as error:
            QMessageBox.warning(
                self,
                self.t("无法保存项目", "Could Not Save Project"),
                self.error_text(error),
            )
            return False
        self.project_path = path.resolve()
        self.settings.setValue("projectDirectory", str(self.project_path.parent))
        self.setWindowTitle(f"{APP_NAMES[self.language]} — {self.project_path.stem}")
        return True

    def _open_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self.t("打开项目", "Open Project"),
            self._last_directory("projectDirectory"),
            self.t("3D 轨迹项目 (*.3dtrack)", "3D Track projects (*.3dtrack)"),
        )
        if not filename:
            return
        path = Path(filename)
        try:
            document = read_editor_project(path)
            photo_events = []
            for index, item in enumerate(document["photos"]["events"], 1):
                if not isinstance(item, dict):
                    raise ValueError(f"项目文件中的第 {index} 个照片设置必须是 JSON 对象")
                try:
                    event = PhotoEvent(**item)
                    event.validate()
                except (TypeError, ValueError) as error:
                    raise ValueError(f"项目文件中的第 {index} 个照片设置无效: {error}") from error
                photo_events.append(event)
        except (OSError, ValueError) as error:
            QMessageBox.warning(
                self,
                self.t("无法打开项目", "Could Not Open Project"),
                self.error_text(error),
            )
            return

        self.track_edit.setText(document["track"]["file"])
        self.name_edit.setText(str(document["track"].get("name", "")))
        self.orientation.set_value(document["movie"]["orientation"])
        seconds = document["movie"]["seconds"]
        self.duration_combo.setCurrentText(self.t(f"{seconds:g}秒", f"{seconds:g} sec"))
        self.quality.set_value(document["movie"]["quality"])
        self.media_edit.setText(document["video"]["directory"])
        self.segments = document["video"]["segments"]
        self.photos_edit.setText(document["photos"]["directory"])
        self.photo_events = photo_events
        self.music_edit.setText(document["music"]["file"])
        self.music_start_offset.setValue(float(document["music"].get("start_offset_seconds", 0.0)))
        self.output_edit.setText(document["output"]["directory"])
        self.project_path = path.resolve()
        self.settings.setValue("projectDirectory", str(self.project_path.parent))
        self.setWindowTitle(f"{APP_NAMES[self.language]} — {self.project_path.stem}")
        self._update_summary()

    def _choose_track(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self.t("选择轨迹文件", "Choose Track File"),
            self._last_directory("trackDirectory"),
            self.t("轨迹文件 (*.fit *.FIT *.kml *.KML)", "Track files (*.fit *.FIT *.kml *.KML)"),
        )
        if not filename:
            return
        path = Path(filename)
        self.track_edit.setText(str(path))
        self.settings.setValue("trackDirectory", str(path.parent))
        if not self.name_edit.text().strip():
            self.name_edit.setText(path.stem.replace("_", " "))
        self._update_status()

    def _choose_media_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            self.t("选择影片文件夹", "Choose Video Folder"),
            self._last_directory("mediaDirectory"),
        )
        if not directory:
            return
        path = Path(directory)
        current_directory = self.media_edit.text().strip()
        if not current_directory or path != Path(current_directory):
            self.segments = []
        self.media_edit.setText(str(path))
        self.settings.setValue("mediaDirectory", str(path))
        self._update_summary()

    def _choose_music(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self.t("选择背景音乐", "Choose Background Music"),
            self._last_directory("musicDirectory"),
            self.t(
                "音频文件 (*.mp3 *.wav *.m4a *.aac *.flac)",
                "Audio files (*.mp3 *.wav *.m4a *.aac *.flac)",
            ),
        )
        if filename:
            path = Path(filename)
            self.music_edit.setText(str(path))
            self.settings.setValue("musicDirectory", str(path.parent))

    def _photo_directory(self) -> Path | None:
        value = self.photos_edit.text().strip()
        return Path(value).expanduser() if value else None

    def _choose_photo_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, self.t("选择照片文件夹", "Choose Photo Folder"),
            self._last_directory("photoDirectory"),
        )
        if directory:
            if directory != self.photos_edit.text().strip():
                self.photo_events = []
            self.photos_edit.setText(directory)
            self.settings.setValue("photoDirectory", directory)

    def _update_photo_summary(self) -> None:
        directory = self._photo_directory()
        self.edit_photos_button.setEnabled(bool(directory and directory.is_dir()))
        if directory and directory.is_dir():
            count = len(list_photo_files(directory))
            enabled = sum(event.enabled for event in self.photo_events)
            message = self.t(f"已找到 {count} 张照片，已勾选 {enabled} 张",
                             f"Found {count} photos; {enabled} checked")
        elif directory:
            message = self.t("照片文件夹不存在", "Photo folder does not exist")
        else:
            message = self.t("尚未选择照片文件夹（可选）", "No photo folder selected (optional)")
        self.photo_summary.setText(message)

    def _edit_photos(self) -> None:
        directory = self._photo_directory()
        if directory is None:
            return
        try:
            files = list_photo_files(directory)
        except OSError as error:
            QMessageBox.warning(self, self.t("无法打开照片", "Could Not Open Photos"), str(error))
            return
        if not files and not self.photo_events:
            QMessageBox.information(self, self.t("没有找到照片", "No Photos Found"), self.t(
                "这个文件夹中没有 JPG、JPEG、PNG、HEIC 或 HEIF 照片。",
                "This folder contains no JPG, JPEG, PNG, HEIC, or HEIF photos.",
            ))
            return
        activity = None
        track = Path(self.track_edit.text().strip())
        if track.is_file():
            try:
                metadata = prepare(track, None)
                activity = tuple(activity_wall_time(metadata[key]) for key in ("start", "end"))
            except (OSError, ValueError, RuntimeError, SyntaxError) as error:
                QMessageBox.warning(
                    self, self.t("无法读取活动时间", "Could Not Read Activity Time"), self.error_text(error)
                )
        groups = []
        if self.segments:
            video_dir = Path(self.media_edit.text().strip())
            try:
                clips, errors, _ = load_configured_segments(self.segments, video_dir)
                if errors:
                    raise ValueError("\n".join(errors))
                groups = list(enumerate(group_segments(clips, VIDEO_GROUP_WINDOW), 1))
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                QMessageBox.warning(self, self.t(
                    "预计时间无法计入影片片段", "Estimates Will Exclude Video Clips"
                ), self.error_text(error))
        try:
            seconds = self._duration()
        except ValueError as error:
            QMessageBox.warning(self, self.t("请检查影片时长", "Check Movie Duration"), self.error_text(error))
            return
        bounds = popup_safe_bounds(*output_dimensions(self.orientation.value(), self.quality.value()))
        dialog = PhotoEditorDialog(directory, files, self.photo_events, activity, groups, seconds, bounds,
                                   self, language=self.language)
        if dialog.exec() == QDialog.Accepted:
            self.photo_events = dialog.events
            self._update_photo_summary()

    def _choose_output_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            self.t("选择输出位置", "Choose Output Location"),
            self._last_directory("outputDirectory", str(default_output_directory())),
        )
        if directory:
            self.output_edit.setText(directory)
            self.settings.setValue("outputDirectory", directory)
            self._update_status()

    def _edit_segments(self) -> None:
        directory = Path(self.media_edit.text().strip())
        if not directory.is_dir():
            QMessageBox.information(
                self,
                self.t("请先选择影片文件夹", "Choose a Video Folder First"),
                self.t(
                    "请选择包含实拍影片的文件夹。",
                    "Choose a folder containing your source videos.",
                ),
            )
            return
        if not list_video_files(directory):
            QMessageBox.information(
                self,
                self.t("没有找到影片", "No Videos Found"),
                self.t(
                    "这个文件夹中没有找到 MP4、MOV 或 M4V 影片。",
                    "No MP4, MOV, or M4V videos were found in this folder.",
                ),
            )
            return
        dialog = ClipEditorDialog(directory, self.segments, self, language=self.language)
        if dialog.exec() == QDialog.Accepted:
            self.segments = dialog.segments
            self._update_summary()

    def _update_summary(self) -> None:
        self._update_photo_summary()
        directory = Path(self.media_edit.text().strip()) if self.media_edit.text().strip() else None
        count = len(list_video_files(directory)) if directory else 0
        if count:
            self.summary_label.setText(self.t(
                f"已找到 {count} 部影片，已选择 {len(self.segments)} 个片段",
                f"Found {count} videos; {len(self.segments)} clips selected",
            ))
            self.edit_segments_button.setEnabled(True)
        else:
            self.summary_label.setText(self.t(
                "尚未选择影片文件夹（可选）", "No video folder selected (optional)"
            ))
            self.edit_segments_button.setEnabled(False)
        self._update_status()

    def _update_status(self) -> None:
        track = Path(self.track_edit.text().strip())
        output = Path(self.output_edit.text().strip()) if self.output_edit.text().strip() else None
        if not track.is_file():
            self.status_label.setText(self.t("●  请选择轨迹文件", "●  Select a track file"))
        elif not self.name_edit.text().strip():
            self.status_label.setText(self.t("●  请填写活动名称", "●  Enter an activity name"))
        elif not output:
            self.status_label.setText(self.t("●  请选择输出位置", "●  Choose an output location"))
        else:
            self.status_label.setText(self.t(
                "●  素材准备完成，可以开始生成",
                "●  Media is ready; you can generate the movie",
            ))

    def _duration(self) -> float:
        match = re.search(r"\d+(?:\.\d+)?", self.duration_combo.currentText())
        if not match:
            raise ValueError(self.t("请输入有效的影片时长", "Enter a valid movie duration."))
        return float(match.group())

    def _build_config(self, preview: bool) -> tuple[dict, Path, Path]:
        track = Path(self.track_edit.text().strip())
        media_directory = Path(self.media_edit.text().strip()) if self.media_edit.text().strip() else None
        music_file = Path(self.music_edit.text().strip()) if self.music_edit.text().strip() else None
        photo_directory = self._photo_directory()
        output_value = self.output_edit.text().strip()
        if not output_value:
            raise ValueError(self.t("请选择输出位置", "Choose an output location."))
        output_directory = Path(output_value)
        output_directory.mkdir(parents=True, exist_ok=True)
        if photo_directory and not preview:
            if not photo_directory.is_dir():
                raise ValueError(self.t("照片文件夹不存在", "Photo folder does not exist"))
        config, final_output = build_project_config(
            track_file=track,
            activity_name=self.name_edit.text(),
            orientation=self.orientation.value(),
            quality=self.quality.value(),
            seconds=self._duration(),
            output_directory=output_directory,
            media_directory=media_directory,
            segments=self.segments,
            photo_directory=photo_directory,
            photo_events=[asdict(event) for event in self.photo_events],
            music_file=music_file,
            music_start_offset_seconds=self.music_start_offset.value(),
            preview=preview,
        )
        suffix = "preview-project.json" if preview else "project.json"
        config_path = output_directory / ".3d_track_work" / f"{safe_filename(self.name_edit.text())}-{suffix}"
        write_project_config(config_path, config)
        return config, config_path, final_output

    def _preflight(self) -> None:
        missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
        if missing:
            raise ValueError(self.t(
                "缺少必要程序：" + "、".join(missing),
                "Required programs are missing: " + ", ".join(missing),
            ))
        if not (ROOT / "node_modules" / "cesium" / "Build" / "Cesium" / "Cesium.js").is_file():
            raise ValueError(self.t(
                "缺少 CesiumJS，请先在项目目录运行 npm install",
                "CesiumJS is missing. Run npm install in the project directory first.",
            ))

    def _start_render(self, preview: bool) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            QMessageBox.information(
                self,
                self.t("正在生成", "Generation in Progress"),
                self.t(
                    "请等待当前任务完成，或先取消当前任务。",
                    "Wait for the current task to finish, or cancel it first.",
                ),
            )
            return
        try:
            if not preview and not self._save_project():
                return
            self._preflight()
            _config, config_path, final_output = self._build_config(preview)
        except (OSError, ValueError) as error:
            QMessageBox.warning(
                self,
                self.t("无法开始生成", "Could Not Start Generation"),
                self.error_text(error),
            )
            return
        if not preview and final_output.exists():
            answer = QMessageBox.question(
                self,
                self.t("影片已经存在", "Movie Already Exists"),
                self.t(
                    f"输出位置已经有同名影片：\n{final_output.name}\n\n是否覆盖？",
                    f"A movie with the same name already exists:\n{final_output.name}\n\nOverwrite it?",
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        self.is_preview = preview
        self.expected_output = final_output
        self.progress_dialog = RenderDialog(
            self.t("快速预览", "Quick Preview")
            if preview else self.t("生成影片", "Generate Movie"),
            self,
            language=self.language,
        )
        self.progress_dialog.cancel_button.clicked.connect(self._cancel_render)
        self.progress_dialog.show()

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(WORK_ROOT))
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_process_output)
        self.process.finished.connect(self._render_finished)
        arguments = ["--generate-from-config", str(config_path)] if IS_BUNDLED else [
            str(ROOT / "generate_from_config.py"), str(config_path)
        ]
        self.process.start(render_worker_executable(), arguments)

    def _read_process_output(self) -> None:
        if not self.process or not self.progress_dialog:
            return
        output = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not output:
            return
        self.progress_dialog.log.appendPlainText(output.rstrip())
        lines = [line for line in output.splitlines() if line.strip()]
        if lines:
            line = lines[-1]
            self.progress_dialog.status.setText(line[:110])
            match = re.search(r"截帧\s+(\d+)/(\d+)", line)
            if match:
                current, total = map(int, match.groups())
                self.progress_dialog.progress.setRange(0, total)
                self.progress_dialog.progress.setValue(current)

    def _cancel_render(self) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
        if self.progress_dialog:
            self.progress_dialog.reject()

    def _render_finished(self, exit_code: int, _status) -> None:
        dialog = self.progress_dialog
        output = self.expected_output
        if dialog:
            dialog.cancel_button.setText(self.t("关闭", "Close"))
            try:
                dialog.cancel_button.clicked.disconnect()
            except RuntimeError:
                pass
            dialog.cancel_button.clicked.connect(dialog.accept)
            if exit_code == 0 and output and output.is_file():
                dialog.status.setText(
                    self.t("预览生成完成", "Preview Complete")
                    if self.is_preview else self.t("影片生成完成", "Movie Complete")
                )
                dialog.progress.setRange(0, 1)
                dialog.progress.setValue(1)
                open_button = QPushButton(self.t("打开影片", "Open Movie"))
                open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(output))))
                dialog.layout().itemAt(dialog.layout().count() - 1).layout().insertWidget(1, open_button)
            else:
                dialog.status.setText(self.t(
                    f"生成失败（退出代码 {exit_code}）",
                    f"Generation failed (exit code {exit_code})",
                ))
                QMessageBox.critical(
                    self,
                    self.t("生成失败", "Generation Failed"),
                    self.t(
                        "请查看生成窗口中的详细信息。",
                        "See the generation window for details.",
                    ),
                )
        self.process = None
        self._update_status()

    def _clear_form(self) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            QMessageBox.information(
                self,
                self.t("正在生成", "Generation in Progress"),
                self.t("请先等待当前任务结束。", "Wait for the current task to finish."),
            )
            return
        self.track_edit.clear()
        self.name_edit.clear()
        self.media_edit.clear()
        self.photos_edit.clear()
        self.music_edit.clear()
        self.music_start_offset.setValue(0.0)
        self.segments = []
        self.photo_events = []
        self.project_path = None
        self.setWindowTitle(APP_NAMES[self.language])
        self.orientation.set_value("landscape")
        self.quality.set_value("1080p")
        self.duration_combo.setCurrentText(self.t("30秒", "30 sec"))
        self._update_summary()

    def _restore_settings(self) -> None:
        output = self._last_directory("outputDirectory", str(default_output_directory()))
        self.output_edit.setText(output)

    def closeEvent(self, event) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            answer = QMessageBox.question(
                self,
                self.t("任务仍在运行", "Task Still Running"),
                self.t(
                    "要取消当前任务并退出吗？",
                    "Cancel the current task and exit?",
                ),
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._cancel_render()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAMES[system_language()])
    app.setOrganizationName("3DTrackMovie")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    bundled_commands = {
        "--generate-from-config": ("generate_from_config", "main"),
        "--render-video": ("render_video", "main"),
        "--compose-media-video": ("compose_media_video", "main"),
        "--mix-music": ("mix_music", "main"),
    }
    command = sys.argv[1] if len(sys.argv) > 1 else None
    if IS_BUNDLED and command in bundled_commands:
        # Windows pipes can default to a legacy code page instead of UTF-8.
        for stream in (sys.stdout, sys.stderr):
            if stream is not None:
                stream.reconfigure(encoding="utf-8", errors="replace")
        module_name, function_name = bundled_commands[command]
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        module = __import__(module_name)
        raise SystemExit(getattr(module, function_name)())
    raise SystemExit(main())
