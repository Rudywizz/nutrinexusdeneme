from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame

class LabsPlaceholderScreen(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        card = QFrame(objectName="Card")
        v = QVBoxLayout(card)
        v.addWidget(QLabel("Kan Tahlili", objectName="CardTitle"))
        info = QLabel("Sprint-5'te: PDF yükle, e-Nabız formatını otomatik ayıkla, renklendir, onay ekranı.")
        info.setStyleSheet("color:#B8C7D1;")
        v.addWidget(info)
        v.addStretch(1)
        layout.addWidget(card)
        layout.addStretch(1)
