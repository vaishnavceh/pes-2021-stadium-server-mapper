from __future__ import annotations

from core.models import KPIStatistics
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


class KPICard(QFrame):
    """Single Dashboard KPI Card."""

    def __init__(self, title: str, object_name: str, color: str, subtext: str, parent=None):
        super().__init__(parent)
        self.setObjectName("DashboardCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("KPICardTitle")
        layout.addWidget(lbl_title)

        self.lbl_value = QLabel("0")
        self.lbl_value.setObjectName(object_name)
        self.lbl_value.setStyleSheet(f"color: {color}; font-size: 26px; font-weight: bold;")
        layout.addWidget(self.lbl_value)

        lbl_sub = QLabel(subtext)
        lbl_sub.setObjectName("KPICardSubtext")
        layout.addWidget(lbl_sub)

    def set_value(self, val: int) -> None:
        self.lbl_value.setText(str(val))


class Dashboard(QFrame):
    """
    Top Dashboard Container holding 4 KPI Cards:
    TOTAL STADIUMS, HIGH CONFIDENCE, NEEDS REVIEW, UNRESOLVED.
    Calculates statistics directly from authoritative StadiumState models.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.card_total = KPICard("TOTAL STADIUMS", "KPICardValueTotal", "#19A7FF", "Discovered in Directory")
        layout.addWidget(self.card_total)

        self.card_accept = KPICard("HIGH CONFIDENCE", "KPICardValueAccept", "#35D07F", "Auto-Accepted Mappings")
        layout.addWidget(self.card_accept)

        self.card_review = KPICard("NEEDS REVIEW", "KPICardValueReview", "#FFB547", "Requires User Verification")
        layout.addWidget(self.card_review)

        self.card_unresolved = KPICard("UNRESOLVED", "KPICardValueUnresolved", "#FF5C6C", "Missing Team Match")
        layout.addWidget(self.card_unresolved)

    def update_metrics(self, stats: KPIStatistics) -> None:
        """Update all 4 KPI card values from authoritative KPIStatistics."""
        self.card_total.set_value(stats.total)
        self.card_accept.set_value(stats.resolved + stats.manual)
        self.card_review.set_value(stats.review)
        self.card_unresolved.set_value(stats.unresolved)
