"""Desktop editor for photo popups keyed to activity time."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from PySide6.QtCore import QSignalBlocker, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app_config import DEFAULT_FPS, INTRO_RATIO, OUTRO_RATIO, format_timecode
from compose_media_video import plan_media_events
from photo_events import (
    DEFAULT_PHOTO_SECONDS, PHOTO_READ_ERRORS, PhotoEvent, frame_photo, load_photo_image,
    photo_time, read_capture_time,
)


def pixmap(image):
    data = image.tobytes()
    return QPixmap.fromImage(QImage(data, image.width, image.height, image.width * 3, QImage.Format_RGB888))


class PhotoEditorDialog(QDialog):
    def __init__(self, directory, files, saved, activity, video_groups, seconds, bounds,
                 parent=None, *, language="zh"):
        super().__init__(parent)
        self.language = language
        self.directory = directory
        self.activity = activity
        self.video_groups = video_groups
        self.seconds = seconds
        scale = min(440 / bounds[0], 390 / bounds[1])
        self.preview_size = tuple(max(2, round(value * scale)) for value in bounds)
        previous = {event.file: event for event in saved}
        self.events = [previous.pop(path.name, PhotoEvent(path.name)) for path in files]
        self.events.extend(previous.values())
        self.metadata = {}
        self.failures = {}
        self.preview_image = None
        for event in self.events:
            try:
                self.metadata[event.file] = read_capture_time(directory / event.file)
            except PHOTO_READ_ERRORS as exc:
                self.failures[event.file] = str(exc)

        self.setWindowTitle(self.t("编辑照片", "Edit Photos"))
        self.resize(1170, 680)
        layout = QVBoxLayout(self)
        note = QLabel(self.t(
            "勾选要加入的照片。照片出现时地图暂停，成片会增加相应时长。",
            "Check the photos to include. The map pauses during each photo, extending the movie.",
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        if not activity:
            layout.addWidget(QLabel(self.t(
                "选好带时间的轨迹文件后，这里会显示活动进度和预计成片时间。",
                "Select a timestamped track to see route progress and estimated movie times here.",
            )))
        toolbar = QHBoxLayout()
        for zh, en, action in (
            ("勾选活动内照片", "Select In-Range Photos", self._select_in_range),
            ("取消全部勾选", "Uncheck All", self._clear_selection),
            ("批量设为 5 秒", "Set All to 5 Sec", self._reset_durations),
            ("批量偏移时间…", "Shift All Times…", self._shift_times),
        ):
            button = QPushButton(self.t(zh, en))
            button.clicked.connect(action)
            if action == self._select_in_range:
                button.setEnabled(bool(activity))
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        self.table = QTableWidget(len(self.events), 5)
        self.table.setHorizontalHeaderLabels([
            self.t("加入 / 照片", "Include / Photo"), self.t("拍摄时间", "Capture Time"),
            self.t("时长", "Duration"), self.t("轨迹", "Route"), self.t("成片约", "Est. Movie Time"),
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setIconSize(QSize(36, 30))
        self.table.verticalHeader().setDefaultSectionSize(35)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for row, event in enumerate(self.events):
            for col, value in enumerate((event.file, "", "", "", "")):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                self.table.setItem(row, col, item)
        splitter.addWidget(self.table)

        panel = QWidget()
        side = QVBoxLayout(panel)
        self.preview = QLabel(alignment=Qt.AlignCenter)
        self.preview.setMinimumSize(*self.preview_size)
        self.preview.setStyleSheet("background: #191e22; color: white;")
        side.addWidget(self.preview, 1)
        form = QFormLayout()
        self.place_at_end = QCheckBox(self.t("接在最后一个影片片段后", "After Last Video Clip"))
        # Fusion draws the indicator from the palette even on a light-styled dialog.
        checkbox_palette = self.place_at_end.palette()
        checkbox_palette.setColor(QPalette.Base, QColor("#ffffff"))
        checkbox_palette.setColor(QPalette.Window, QColor("#f4f5f4"))
        checkbox_palette.setColor(QPalette.Text, QColor("#20262d"))
        self.place_at_end.setPalette(checkbox_palette)
        self.place_at_end.setToolTip(self.t(
            "照片紧接在最后播放的已选影片片段后，显示结束后继续轨迹。",
            "Show the photo immediately after the last selected video clip plays, then resume the route.",
        ))
        form.addRow(self.t("插入位置", "Position"), self.place_at_end)
        self.time_edit = QLineEdit(placeholderText="YYYY-MM-DD HH:MM:SS")
        form.addRow(self.t("拍摄时间（北京时间）", "Capture Time (UTC+08)"), self.time_edit)
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.reset_time = QPushButton(self.t("恢复 EXIF 时间", "Use EXIF Time"))
        time_status = QHBoxLayout()
        time_status.addWidget(self.source_label, 1)
        time_status.addWidget(self.reset_time)
        form.addRow(time_status)
        self.duration_edit = QDoubleSpinBox()
        self.duration_edit.setRange(0.1, 3600)
        self.duration_edit.setDecimals(2)
        self.duration_edit.setSingleStep(0.5)
        self.duration_edit.setSuffix(self.t(" 秒", " sec"))
        form.addRow(self.t("显示时长", "Display Duration"), self.duration_edit)
        self.framing = QComboBox()
        self.framing.addItem(self.t("完整显示（模糊补边）", "Fit with Blurred Edges"), "fit")
        self.framing.addItem(self.t("铺满（裁切）", "Fill and Crop"), "fill")
        form.addRow(self.t("照片显示方式", "Framing"), self.framing)
        side.addLayout(form)
        navigation = QHBoxLayout()
        for step, label in ((-1, self.t("上一张", "Previous")), (1, self.t("下一张", "Next"))):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, move=step: self._move(move))
            navigation.addWidget(button)
        side.addLayout(navigation)
        splitter.addWidget(panel)
        splitter.setSizes([650, 460])

        footer = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        footer.addWidget(self.summary, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(self.t("保存照片", "Save Photos"))
        buttons.button(QDialogButtonBox.Cancel).setText(self.t("取消", "Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        layout.addLayout(footer)

        self.refresh_timer = QTimer(self, interval=140, singleShot=True)
        self.refresh_timer.timeout.connect(self._refresh)
        self.table.itemChanged.connect(self._check_changed)
        self.table.currentCellChanged.connect(self._load_row)
        self.time_edit.textEdited.connect(self._edit_time)
        self.reset_time.clicked.connect(self._reset_current_time)
        self.place_at_end.toggled.connect(self._change_placement)
        self.duration_edit.valueChanged.connect(lambda value: self._edit_current(duration=value))
        self.framing.currentIndexChanged.connect(self._change_framing)
        self.thumbnail_rows = set()
        self.thumbnail_timer = QTimer(self, interval=25)
        self.thumbnail_timer.timeout.connect(self._load_thumbnail)
        self.table.verticalScrollBar().valueChanged.connect(lambda _: self.thumbnail_timer.start())
        self._refresh()
        self.table.selectRow(0)
        self.thumbnail_timer.start()

    def t(self, chinese, english):
        return chinese if self.language == "zh" else english

    def _timestamp(self, event):
        try:
            return photo_time(event.capture_time) if event.capture_time is not None else self.metadata.get(event.file)
        except ValueError:
            return None

    def _eligible(self, event, timestamp):
        if event.file in self.failures:
            return False
        if event.placement == "end":
            return bool(self.video_groups)
        return (
            timestamp is not None
            and (not self.activity or self.activity[0] <= timestamp <= self.activity[1])
        )

    def _refresh(self):
        rows = [(event, self._timestamp(event)) for event in self.events]
        photos = [
            {
                "path": self.directory / event.file,
                "created": time,
                "duration": event.duration,
                "framing": event.framing,
                "placement": event.placement,
            }
            for event, time in rows if event.enabled and self._eligible(event, time)
        ]
        output_times = {}
        if self.activity and photos:
            plan = plan_media_events(
                self.video_groups, photos, *self.activity, self.seconds,
                {"intro_ratio": INTRO_RATIO, "outro_ratio": OUTRO_RATIO}, DEFAULT_FPS,
            )
            inserted = 0.0
            for event, items in plan:
                if event["type"] == "photo":
                    output_times[event["file"]] = event["base_time"] + inserted
                    inserted += round(items[0]["duration"] * DEFAULT_FPS) / DEFAULT_FPS
                else:
                    inserted += sum(item["duration"] for item in items)
        with QSignalBlocker(self.table):
            for row, (event, timestamp) in enumerate(rows):
                first = self.table.item(row, 0)
                first.setCheckState(Qt.Checked if event.enabled else Qt.Unchecked)
                first.setToolTip(event.file)
                time_item = self.table.item(row, 1)
                if timestamp is not None:
                    time_item.setText(timestamp.isoformat(sep=" ", timespec="seconds"))
                    time_item.setToolTip(timestamp.isoformat(sep=" "))
                else:
                    time_item.setText("—" if event.placement == "end" else self.t("待填写", "Needs Time"))
                    time_item.setToolTip("")
                self.table.item(row, 2).setText(f"{event.duration:g} s")
                status = "—"
                if event.file in self.failures:
                    status = self.t("读取失败", "Unreadable")
                elif event.placement == "end":
                    status = self.t("末段影片后", "After Last Clip") if self.video_groups else self.t(
                        "缺少影片片段", "No Video Clip"
                    )
                elif timestamp is not None and self.activity:
                    start, end = self.activity
                    if start <= timestamp <= end:
                        fraction = (timestamp - start).total_seconds() / max(0.001, (end - start).total_seconds())
                        status = f"{fraction:.1%}"
                    else:
                        status = self.t("活动外", "Out of Range")
                self.table.item(row, 3).setText(status)
                position = output_times.get(event.file)
                self.table.item(row, 4).setText(format_timecode(position) if position is not None else "—")
        selected = sum(event.enabled for event in self.events)
        skipped = selected - len(photos)
        duration = sum(round(photo["duration"] * DEFAULT_FPS) / DEFAULT_FPS for photo in photos)
        self.summary.setText(self.t(
            f"已勾选 {selected} 张 · 可加入 {len(photos)} 张 · 增加 {duration:g} 秒",
            f"{selected} checked · {len(photos)} ready · adds {duration:g} sec",
        ) + (self.t(f" · {skipped} 张需检查", f" · {skipped} need review") if skipped else ""))
        self._show_source()

    def _show_source(self):
        row = self.table.currentRow()
        if row < 0:
            return
        event = self.events[row]
        if event.file in self.failures:
            label = self.t("读取失败", "Unreadable") + " · " + self.failures[event.file]
        elif event.placement == "end":
            if self.video_groups:
                label = self.t("按影片片段定位，拍摄时间仅供参考。",
                               "Placed by video order. Capture time is informational.")
            else:
                label = self.t("请先选择至少一个可用的影片片段。", "Select at least one playable video clip.")
        elif event.capture_time is not None:
            label = self.t("手动设置", "Manual time") if self._timestamp(event) else self.t(
                "日期或时间格式无效", "Invalid date or time"
            )
        elif self.metadata.get(event.file):
            label = self.t("来自 EXIF", "From EXIF")
        else:
            label = self.t("缺少 EXIF 拍摄时间，请手动填写。", "No EXIF capture time. Enter it manually.")
        self.source_label.setText(label)

    def _load_row(self, row, _col, previous_row, _previous_col):
        if row < 0 or row == previous_row:
            return
        event = self.events[row]
        time = self._timestamp(event)
        shown = event.capture_time
        if shown is None and time:
            shown = time.isoformat(sep=" ")
        with QSignalBlocker(self.place_at_end), QSignalBlocker(self.duration_edit), QSignalBlocker(self.framing):
            self.time_edit.setText(shown or "")
            self.place_at_end.setChecked(event.placement == "end")
            self.duration_edit.setValue(event.duration)
            self.framing.setCurrentIndex(self.framing.findData(event.framing))
        self.time_edit.setEnabled(event.placement != "end")
        self.reset_time.setEnabled(event.placement != "end")
        self.preview_image = None
        try:
            self.preview_image = load_photo_image(self.directory / event.file, max(self.preview_size))
            self._set_thumbnail(row, self.preview_image)
        except PHOTO_READ_ERRORS as exc:
            self.failures[event.file] = str(exc)
        self._show_preview()
        self._refresh()

    def _show_preview(self):
        row = self.table.currentRow()
        if self.preview_image is None:
            self.preview.setText(self.t("无法预览照片", "Photo Preview Unavailable"))
        else:
            self.preview.setPixmap(pixmap(frame_photo(
                self.preview_image, self.preview_size, self.events[row].framing
            )))

    def _set_thumbnail(self, row, image):
        thumb = image.copy()
        thumb.thumbnail((36, 30))
        with QSignalBlocker(self.table):
            self.table.item(row, 0).setIcon(QIcon(pixmap(thumb)))
        self.thumbnail_rows.add(row)

    def _load_thumbnail(self):
        first = max(0, self.table.rowAt(0))
        last = self.table.rowAt(self.table.viewport().height() - 1)
        if last < 0:
            last = self.table.rowCount() - 1
        for row in range(first, last + 1):
            if row in self.thumbnail_rows:
                continue
            event = self.events[row]
            self.thumbnail_rows.add(row)
            if event.file not in self.failures:
                try:
                    self._set_thumbnail(row, load_photo_image(self.directory / event.file, 72))
                except PHOTO_READ_ERRORS as exc:
                    self.failures[event.file] = str(exc)
                    self.refresh_timer.start()
            return
        self.thumbnail_timer.stop()

    def _edit_current(self, **values):
        row = self.table.currentRow()
        if row >= 0:
            self.events[row] = replace(self.events[row], **values)
            self.refresh_timer.start()

    def _edit_time(self, text):
        self._edit_current(capture_time=text.strip() or None)

    def _change_placement(self, checked):
        self._edit_current(placement="end" if checked else "timeline")
        self.time_edit.setEnabled(not checked)
        self.reset_time.setEnabled(not checked)
        self._show_source()

    def _reset_current_time(self):
        row = self.table.currentRow()
        self._edit_current(capture_time=None)
        time = self.metadata.get(self.events[row].file)
        self.time_edit.setText(time.isoformat(sep=" ") if time else "")

    def _change_framing(self):
        self._edit_current(framing=self.framing.currentData())
        self._show_preview()

    def _check_changed(self, item):
        if item.column() == 0:
            self.events[item.row()] = replace(self.events[item.row()], enabled=item.checkState() == Qt.Checked)
            self.refresh_timer.start()

    def _move(self, amount):
        self.table.selectRow(min(len(self.events) - 1, max(0, self.table.currentRow() + amount)))

    def _select_in_range(self):
        self.events = [
            replace(event, enabled=True)
            if event.placement == "timeline" and self._eligible(event, self._timestamp(event))
            else event
            for event in self.events
        ]
        self._refresh()

    def _clear_selection(self):
        self.events = [replace(event, enabled=False) for event in self.events]
        self._refresh()

    def _reset_durations(self):
        self.events = [replace(event, duration=DEFAULT_PHOTO_SECONDS) for event in self.events]
        self.duration_edit.setValue(DEFAULT_PHOTO_SECONDS)
        self._refresh()

    def _shift_times(self):
        offset, ok = QInputDialog.getInt(
            self, self.t("批量偏移时间", "Shift All Photo Times"),
            self.t("偏移秒数（可为负值，1 小时 = 3600 秒）", "Offset in seconds (negative allowed, 3600 = 1 hour)"),
            0, -604800, 604800,
        )
        if not ok or not offset:
            return
        try:
            shifted = [
                replace(event, capture_time=(timestamp + timedelta(seconds=offset)).isoformat(sep=" "))
                if timestamp is not None else event
                for event, timestamp in ((event, self._timestamp(event)) for event in self.events)
            ]
        except OverflowError:
            QMessageBox.warning(self, self.t("无法偏移", "Could Not Shift Time"),
                                self.t("偏移后日期超出范围。", "An adjusted date is out of range."))
            return
        self.events = shifted
        self._load_row(self.table.currentRow(), 0, -1, -1)

    def accept(self):
        for row, event in enumerate(self.events):
            try:
                event.validate()
                if event.enabled and (
                    event.file in self.failures
                    or (event.placement == "timeline" and self._timestamp(event) is None)
                ):
                    raise ValueError(self.t(
                        "请补填时间，或取消勾选无法读取的照片。",
                        "Set the capture time or uncheck photos that cannot be read.",
                    ))
            except ValueError as exc:
                self.table.selectRow(row)
                QMessageBox.warning(self, self.t("无法保存照片", "Could Not Save Photos"), f"{event.file}\n{exc}")
                return
        super().accept()
