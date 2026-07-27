from PyQt5.QtCore import Qt, QTimer, QRect, QRectF
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QLinearGradient
import math
from PyQt5.QtWidgets import QProgressBar


class RoundedProgressBar(QProgressBar):
    """Custom progress bar with rounded fill and animated indeterminate balls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(False)
        self._hide_track_when_indeterminate = True
        self._animation_timer = None
        self._sheen_timer = None
        self._sheen_position = 0
        self._gradient_index = 0
        self._edge_bump_count = 0
        self._trail_balls = 5
        self._ball_positions = []
        self._ball_velocities = []
        self._ball_gradients = []
        self._ball_diameter = 0
        self._ball_gap = 24
        self._motion_phase = 0.0
        self._motion_speed = 0.05
        self._speed_ramp_amp = 0.45
        self._speed_ramp_min = 0.4
        self._speed_ramp_boost = 0.85
        self._pre_ramp_boost_1 = 0.2
        self._pre_ramp_boost_2 = 0.45
        self._prev_motion_dir = 1
        self._spread_amp = 1.35
        self._last_bump_count = 0
        self._gradients = [
            ("#833AB4", "#FD1D1D"),
            ("#1FA2FF", "#12D8FA"),
            ("#3A1C71", "#D76D77"),
            ("#11998E", "#38EF7D"),
            ("#FC4A1A", "#F7B733"),
            ("#00C6FF", "#0072FF"),
            ("#F7971E", "#FFD200"),
            ("#8E2DE2", "#4A00E0"),
            ("#F953C6", "#B91D73"),
            ("#36D1DC", "#5B86E5"),
            ("#F12711", "#F5AF19"),
            ("#00F260", "#0575E6"),
            ("#DA4453", "#89216B"),
            ("#43C6AC", "#191654"),
            ("#FF512F", "#DD2476"),
        ]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_rect = self.rect()
        margin = 2
        available_width = bg_rect.width() - (margin * 2)
        radius = 13

        is_indeterminate = (self.maximum() == 0 and self.minimum() == 0)
        if not (is_indeterminate and self._hide_track_when_indeterminate):
            painter.setBrush(QColor(255, 255, 255, 25))
            painter.setPen(QColor(255, 255, 255, 76))
            painter.drawRoundedRect(bg_rect, 15, 15)
        if is_indeterminate:
            if self._sheen_timer:
                self._sheen_timer.stop()
                self._sheen_timer = None
                self._sheen_position = 0
            if not self._animation_timer:
                self._animation_timer = QTimer(self)
                self._animation_timer.timeout.connect(self._update_animation)
                self._animation_timer.start(30)
                self._edge_bump_count = 0
                self._ball_positions = []
                self._ball_velocities = []
                self._ball_gradients = []
                self._ball_diameter = 0
                self._motion_phase = 0.0
                self._prev_motion_dir = 1

            track_height = bg_rect.height() - (margin * 2)
            ball_diameter = max(8, int(track_height * 0.7))
            max_position = max(0, available_width - ball_diameter)
            if self._ball_diameter != ball_diameter or len(self._ball_positions) != self._trail_balls:
                self._ball_diameter = ball_diameter
                self._ball_positions = [i * (ball_diameter + self._ball_gap) for i in range(self._trail_balls)]
                self._ball_velocities = [0.0] * self._trail_balls
                self._ball_gradients = [self._gradient_index] * self._trail_balls
            base_x = bg_rect.x() + margin
            base_y = bg_rect.y() + margin + (track_height - ball_diameter) // 2

            for i in range(self._trail_balls):
                gradient_index = self._ball_gradients[i] if i < len(self._ball_gradients) else self._gradient_index
                start_color, end_color = self._gradients[gradient_index]
                ball_x = base_x + self._ball_positions[i]
                ball_rect = QRectF(ball_x, base_y, ball_diameter, ball_diameter)
                gradient = QLinearGradient(
                    ball_rect.x(), ball_rect.y(),
                    ball_rect.x() + ball_rect.width(), ball_rect.y()
                )
                gradient.setColorAt(0, QColor(start_color))
                gradient.setColorAt(1, QColor(end_color))
                painter.setBrush(gradient)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(ball_rect)

                t = (self._sheen_position % 1000) / 1000.0
                sheen_width = ball_diameter * 0.65
                sheen_x = ball_rect.x() + (ball_diameter + sheen_width) * t - sheen_width
                sheen_rect = QRectF(sheen_x, ball_rect.y(), sheen_width, ball_rect.height())
                painter.save()
                path = QPainterPath()
                path.addEllipse(ball_rect)
                painter.setClipPath(path)
                sheen_gradient = QLinearGradient(
                    sheen_rect.x(), sheen_rect.y(),
                    sheen_rect.x() + sheen_rect.width(), sheen_rect.y()
                )
                sheen_gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
                sheen_gradient.setColorAt(0.5, QColor(255, 255, 255, 55))
                sheen_gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.fillRect(sheen_rect, sheen_gradient)
                painter.restore()
        else:
            if self._animation_timer:
                self._animation_timer.stop()
                self._animation_timer = None
            if self.value() > 0 and self.maximum() > 0:
                fill_width = int((self.value() / self.maximum()) * available_width)
                if fill_width > 0:
                    if not self._sheen_timer:
                        self._sheen_timer = QTimer(self)
                        self._sheen_timer.timeout.connect(self._update_sheen)
                        self._sheen_timer.start(50)
                    fill_rect = QRect(
                        bg_rect.x() + margin,
                        bg_rect.y() + margin,
                        fill_width,
                        bg_rect.height() - (margin * 2)
                    )
                    gradient = QLinearGradient(fill_rect.x(), fill_rect.y(), fill_rect.x() + fill_rect.width(), fill_rect.y())
                    gradient.setColorAt(0, QColor("#833AB4"))
                    gradient.setColorAt(1, QColor("#FD1D1D"))
                    painter.setBrush(gradient)
                    painter.setPen(Qt.NoPen)
                    path = QPainterPath()
                    path.addRoundedRect(QRectF(fill_rect), radius, radius)
                    painter.fillPath(path, gradient)

                    sheen_width = max(30, int(fill_rect.width() * 0.35))
                    sheen_x = fill_rect.x() + (self._sheen_position % (fill_rect.width() + sheen_width)) - sheen_width
                    sheen_rect = QRectF(sheen_x, fill_rect.y(), sheen_width, fill_rect.height())
                    painter.save()
                    painter.setClipPath(path)
                    sheen_gradient = QLinearGradient(sheen_rect.x(), sheen_rect.y(), sheen_rect.x() + sheen_rect.width(), sheen_rect.y())
                    sheen_gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
                    sheen_gradient.setColorAt(0.5, QColor(255, 255, 255, 80))
                    sheen_gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
                    painter.fillRect(sheen_rect, sheen_gradient)
                    painter.restore()
            else:
                if self._sheen_timer:
                    self._sheen_timer.stop()
                    self._sheen_timer = None
                    self._sheen_position = 0

    def _update_animation(self):
        width = max(0, self.width() - 4)
        # Keep animation sizing aligned with the smaller indeterminate balls
        ball_diameter = max(8, int((self.height() - 4) * 0.7))
        max_position = max(0, width - ball_diameter)

        if self._trail_balls <= 0:
            return

        if self._trail_balls > 1:
            max_gap = max(2, int((max_position - ball_diameter * self._trail_balls) / (self._trail_balls - 1)))
            # Allow near-touching compression without overlap
            tight_gap = 0
            effective_gap = min(self._ball_gap, max_gap, tight_gap)
        else:
            effective_gap = 0

        if (len(self._ball_positions) != self._trail_balls or
                len(self._ball_velocities) != self._trail_balls):
            self._ball_positions = [i * (ball_diameter + effective_gap) for i in range(self._trail_balls)]
            self._ball_velocities = [0.0] * self._trail_balls
            self._ball_gradients = [self._gradient_index] * self._trail_balls
            self._motion_phase = 0.0
            self._prev_motion_dir = 1
            self._edge_bump_count = 0
            self._last_bump_count = 0

        # Timer-driven motion: move the chain back and forth smoothly
        current_pos = (1 + math.sin(self._motion_phase)) / 2
        current_expand = math.sin(math.pi * current_pos)
        ramp_min = max(self._speed_ramp_min, 1.0 - self._speed_ramp_amp)
        ramp_max = 1.0 + self._speed_ramp_boost
        base_speed_factor = (ramp_min + ramp_max) / 2.0
        bump_phase = self._edge_bump_count % 5
        if bump_phase == 4:
            speed_factor = 1.0 + (self._speed_ramp_boost * (1.0 - current_expand)) - (self._speed_ramp_amp * current_expand)
            speed_factor = max(self._speed_ramp_min, speed_factor)
        elif bump_phase == 3:
            speed_factor = base_speed_factor * (1.0 + self._pre_ramp_boost_2)
        elif bump_phase == 2:
            speed_factor = base_speed_factor * (1.0 + self._pre_ramp_boost_1)
        else:
            speed_factor = base_speed_factor
        self._motion_phase += self._motion_speed * speed_factor
        if self._motion_phase > 2 * math.pi:
            self._motion_phase -= 2 * math.pi

        pos_norm = (1 + math.sin(self._motion_phase)) / 2
        # Expand during mid-travel, return to base spacing near edges
        expand_profile = math.sin(math.pi * pos_norm)
        spread_factor = 1.0 + (self._spread_amp * expand_profile)
        gap = (ball_diameter + effective_gap) * spread_factor
        chain_length = (self._trail_balls - 1) * gap
        max_chain_start = max(0, max_position - chain_length)
        chain_start = max_chain_start * pos_norm
        for i in range(self._trail_balls):
            self._ball_positions[i] = chain_start + i * gap

        motion_dir = 1 if math.cos(self._motion_phase) >= 0 else -1
        if motion_dir != self._prev_motion_dir:
            self._edge_bump_count += 1
            if self._edge_bump_count % 5 == 0:
                self._gradient_index = (self._gradient_index + 1) % len(self._gradients)
            self._ball_gradients = [self._gradient_index] * self._trail_balls
            self._prev_motion_dir = motion_dir

        self._sheen_position = (self._sheen_position + 6) % 1000
        self.update()

    def _update_sheen(self):
        self._sheen_position += 8
        self.update()

