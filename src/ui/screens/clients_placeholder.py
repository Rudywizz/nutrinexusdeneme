from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame

class ClientsPlaceholderScreen(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        card = QFrame(objectName="Card")
        v = QVBoxLayout(card)
        v.addWidget(QLabel("Danışanlar", objectName="CardTitle"))
        info = QLabel("Sprint-1'de: danışan listesi, arama, ekle/düzenle/pasife al gelecek.")
        info.setStyleSheet("color:#B8C7D1;")
        v.addWidget(info)
        v.addStretch(1)
        layout.addWidget(card)
        layout.addStretch(1)
