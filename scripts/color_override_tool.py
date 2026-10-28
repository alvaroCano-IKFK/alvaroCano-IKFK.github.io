"""
color_override_tool.py
----------------------
Herramienta de Maya para asignar los colores oficiales de override (indices 0-31)
a varias shapes a la vez, mediante una paleta visual de swatches.

Uso:
    import color_override_tool
    color_override_tool.show()

Probado en Maya 2024 (PySide2). Compatible con PySide6 (Maya 2025+).
"""

import maya.cmds as cmds
import maya.OpenMayaUI as omui

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance


WINDOW_OBJECT_NAME = "colorOverrideToolWin"

# Gamma aplicada SOLO a la previsualizacion de los swatches.
# 1.0 = valores crudos (como en el Attribute Editor).
# 2.2 = swatches mas claros, parecido a como se ven las curvas en el viewport.
PREVIEW_GAMMA = 1.0

# Los 32 colores del override de Maya (indice: RGB lineal)
MAYA_COLORS = [
    (0.500, 0.500, 0.500),  # 0  gris por defecto
    (0.000, 0.000, 0.000),  # 1
    (0.250, 0.250, 0.250),  # 2
    (0.600, 0.600, 0.600),  # 3
    (0.608, 0.000, 0.157),  # 4
    (0.000, 0.016, 0.373),  # 5
    (0.000, 0.000, 1.000),  # 6
    (0.000, 0.275, 0.098),  # 7
    (0.149, 0.000, 0.263),  # 8
    (0.784, 0.000, 0.784),  # 9
    (0.541, 0.282, 0.200),  # 10
    (0.247, 0.137, 0.121),  # 11
    (0.600, 0.149, 0.000),  # 12
    (1.000, 0.000, 0.000),  # 13
    (0.000, 1.000, 0.000),  # 14
    (0.000, 0.255, 0.600),  # 15
    (1.000, 1.000, 1.000),  # 16
    (1.000, 1.000, 0.000),  # 17
    (0.392, 0.863, 1.000),  # 18
    (0.263, 1.000, 0.639),  # 19
    (1.000, 0.690, 0.690),  # 20
    (0.894, 0.675, 0.475),  # 21
    (1.000, 1.000, 0.388),  # 22
    (0.000, 0.600, 0.329),  # 23
    (0.630, 0.416, 0.189),  # 24
    (0.622, 0.630, 0.189),  # 25
    (0.408, 0.630, 0.189),  # 26
    (0.189, 0.630, 0.363),  # 27
    (0.189, 0.630, 0.630),  # 28
    (0.189, 0.404, 0.630),  # 29
    (0.435, 0.189, 0.630),  # 30
    (0.630, 0.189, 0.416),  # 31
]


# ---------------------------------------------------------------------------
# Logica (independiente de la UI, reutilizable desde tus modulos de rig)
# ---------------------------------------------------------------------------

def collect_targets(nodes=None, hierarchy=False, use_transform=False):
    """Devuelve la lista de nodos a los que aplicar el override.

    nodes         : lista de nodos. Si es None, usa la seleccion actual.
    hierarchy     : incluye toda la descendencia de cada nodo.
    use_transform : aplica al transform en lugar de a sus shapes.
    """
    if nodes is None:
        nodes = cmds.ls(selection=True, objectsOnly=True, long=True) or []

    pool = []
    for node in nodes:
        pool.append(node)
        if hierarchy:
            pool.extend(cmds.listRelatives(node, allDescendents=True, fullPath=True) or [])

    targets = []
    for node in pool:
        is_transform = cmds.objectType(node, isAType="transform")

        if use_transform:
            if is_transform:
                targets.append(node)
            else:
                parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
                targets.extend(parent)
            continue

        if is_transform:
            shapes = cmds.listRelatives(node, shapes=True, fullPath=True,
                                        noIntermediate=True) or []
            targets.extend(shapes)
        else:
            targets.append(node)

    # Fuera intermedios y duplicados, manteniendo el orden
    clean = []
    for node in dict.fromkeys(targets):
        if cmds.attributeQuery("intermediateObject", node=node, exists=True):
            if cmds.getAttr("{0}.intermediateObject".format(node)):
                continue
        clean.append(node)
    return clean


def _can_override(node):
    """(bool, motivo) - comprueba si el nodo admite escribir el override."""
    if not cmds.attributeQuery("overrideEnabled", node=node, exists=True):
        return False, "sin atributos de override"
    if not cmds.getAttr("{0}.overrideEnabled".format(node), settable=True):
        conns = cmds.listConnections("{0}.drawOverride".format(node),
                                     source=True, destination=False) or []
        if conns:
            return False, "controlado por display layer ({0})".format(conns[0])
        return False, "atributo bloqueado o conectado"
    return True, ""


def apply_color(targets, index=None, rgb=None):
    """Aplica un color de override. Usa index (0-31) o rgb (tupla 0-1).

    Devuelve (aplicados, [(nodo, motivo), ...] omitidos).
    """
    done, skipped = [], []
    cmds.undoInfo(openChunk=True, chunkName="applyOverrideColor")
    try:
        for node in targets:
            ok, reason = _can_override(node)
            if not ok:
                skipped.append((node, reason))
                continue
            try:
                cmds.setAttr("{0}.overrideEnabled".format(node), 1)
                if rgb is not None:
                    cmds.setAttr("{0}.overrideRGBColors".format(node), 1)
                    cmds.setAttr("{0}.overrideColorRGB".format(node), *rgb)
                else:
                    cmds.setAttr("{0}.overrideRGBColors".format(node), 0)
                    cmds.setAttr("{0}.overrideColor".format(node), index)
                done.append(node)
            except RuntimeError as exc:
                skipped.append((node, str(exc).strip()))
    finally:
        cmds.undoInfo(closeChunk=True)
    return done, skipped


def clear_override(targets):
    """Desactiva overrideEnabled en los nodos indicados."""
    done, skipped = [], []
    cmds.undoInfo(openChunk=True, chunkName="clearOverrideColor")
    try:
        for node in targets:
            ok, reason = _can_override(node)
            if not ok:
                skipped.append((node, reason))
                continue
            cmds.setAttr("{0}.overrideEnabled".format(node), 0)
            done.append(node)
    finally:
        cmds.undoInfo(closeChunk=True)
    return done, skipped


def read_color(node):
    """Devuelve el indice de override del nodo, o None si no aplica."""
    if not cmds.attributeQuery("overrideEnabled", node=node, exists=True):
        return None
    if not cmds.getAttr("{0}.overrideEnabled".format(node)):
        return None
    if cmds.getAttr("{0}.overrideRGBColors".format(node)):
        return None
    return cmds.getAttr("{0}.overrideColor".format(node))


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


class ColorSwatch(QtWidgets.QPushButton):

    SIZE = 44

    # Senal propia: clicked() emite un bool que se colaria como argumento
    picked = QtCore.Signal(int)

    def __init__(self, index, rgb, parent=None):
        super(ColorSwatch, self).__init__(parent)
        self.index = index
        self.rgb = rgb
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setText(str(index))
        self.setToolTip("Indice {0}\nRGB {1:.3f}, {2:.3f}, {3:.3f}".format(index, *rgb))
        self.set_selected(False)
        self.clicked.connect(self._emit_picked)

    def _emit_picked(self, *args):
        self.picked.emit(self.index)

    def _preview_rgb(self):
        gamma = 1.0 / PREVIEW_GAMMA if PREVIEW_GAMMA else 1.0
        return [int(round(min(1.0, max(0.0, c)) ** gamma * 255)) for c in self.rgb]

    def set_selected(self, state):
        r, g, b = self._preview_rgb()
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        text_color = "#101010" if luminance > 0.55 else "#f0f0f0"
        border = "3px solid #ffb400" if state else "1px solid #1a1a1a"
        self.setStyleSheet(
            "QPushButton {{"
            "  background-color: rgb({r},{g},{b});"
            "  border: {border};"
            "  border-radius: 4px;"
            "  color: {text};"
            "  font-size: 10px;"
            "}}"
            "QPushButton:hover {{ border: 2px solid #ffffff; }}".format(
                r=r, g=g, b=b, border=border, text=text_color)
        )


class ColorOverrideUI(QtWidgets.QDialog):

    COLUMNS = 8

    def __init__(self, parent=None):
        super(ColorOverrideUI, self).__init__(parent or maya_main_window())
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("Override Colors")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(420)

        self._swatches = []
        self._current_index = None
        self._custom_rgb = (1.0, 1.0, 1.0)

        self._build_ui()
        self._connect_signals()

    # -- construccion -------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        palette_box = QtWidgets.QGroupBox("Paleta de Maya (32 indices)")
        grid = QtWidgets.QGridLayout(palette_box)
        grid.setSpacing(4)
        for i, rgb in enumerate(MAYA_COLORS):
            swatch = ColorSwatch(i, rgb)
            swatch.picked.connect(self._on_swatch_clicked)
            grid.addWidget(swatch, i // self.COLUMNS, i % self.COLUMNS)
            self._swatches.append(swatch)
        root.addWidget(palette_box)

        options_box = QtWidgets.QGroupBox("Opciones")
        opts = QtWidgets.QVBoxLayout(options_box)
        self.chk_auto = QtWidgets.QCheckBox("Aplicar al hacer clic en un color")
        self.chk_auto.setChecked(True)
        self.chk_hierarchy = QtWidgets.QCheckBox("Incluir toda la jerarquia")
        self.chk_transform = QtWidgets.QCheckBox("Aplicar al transform en vez de a las shapes")
        for widget in (self.chk_auto, self.chk_hierarchy, self.chk_transform):
            opts.addWidget(widget)
        root.addWidget(options_box)

        buttons = QtWidgets.QHBoxLayout()
        self.btn_apply = QtWidgets.QPushButton("Aplicar")
        self.btn_pick = QtWidgets.QPushButton("Leer seleccion")
        self.btn_rgb = QtWidgets.QPushButton("RGB libre...")
        self.btn_clear = QtWidgets.QPushButton("Quitar override")
        for widget in (self.btn_apply, self.btn_pick, self.btn_rgb, self.btn_clear):
            widget.setMinimumHeight(28)
            buttons.addWidget(widget)
        root.addLayout(buttons)

        self.lbl_status = QtWidgets.QLabel("Selecciona nodos y elige un color.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #999999;")
        root.addWidget(self.lbl_status)

    def _connect_signals(self):
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_pick.clicked.connect(self._on_pick)
        self.btn_rgb.clicked.connect(self._on_custom_rgb)
        self.btn_clear.clicked.connect(self._on_clear)

    # -- helpers ------------------------------------------------------------

    def _targets(self):
        return collect_targets(hierarchy=self.chk_hierarchy.isChecked(),
                               use_transform=self.chk_transform.isChecked())

    def _select_swatch(self, index):
        self._current_index = index
        for swatch in self._swatches:
            swatch.set_selected(swatch.index == index)

    def _report(self, done, skipped, action="Aplicado"):
        msg = "{0} a {1} nodo(s).".format(action, len(done))
        if skipped:
            msg += " Omitidos {0}: {1}".format(
                len(skipped),
                ", ".join("{0} ({1})".format(n.split("|")[-1], r) for n, r in skipped[:3]))
            if len(skipped) > 3:
                msg += "..."
        self.lbl_status.setText(msg)

    # -- slots --------------------------------------------------------------

    def _on_swatch_clicked(self, index):
        self._select_swatch(index)
        if self.chk_auto.isChecked():
            self._on_apply()

    def _on_apply(self):
        if self._current_index is None:
            self.lbl_status.setText("Elige primero un color de la paleta.")
            return
        targets = self._targets()
        if not targets:
            self.lbl_status.setText("No hay nada seleccionado.")
            return
        done, skipped = apply_color(targets, index=self._current_index)
        self._report(done, skipped, "Indice {0} aplicado".format(self._current_index))

    def _on_clear(self):
        targets = self._targets()
        if not targets:
            self.lbl_status.setText("No hay nada seleccionado.")
            return
        done, skipped = clear_override(targets)
        self._report(done, skipped, "Override desactivado")

    def _on_pick(self):
        targets = self._targets()
        if not targets:
            self.lbl_status.setText("No hay nada seleccionado.")
            return
        index = read_color(targets[0])
        if index is None:
            self.lbl_status.setText("{0} no usa color por indice.".format(targets[0].split("|")[-1]))
            return
        self._select_swatch(index)
        self.lbl_status.setText("{0} usa el indice {1}.".format(targets[0].split("|")[-1], index))

    def _on_custom_rgb(self):
        start = QtGui.QColor.fromRgbF(*self._custom_rgb)
        color = QtWidgets.QColorDialog.getColor(start, self, "Color RGB personalizado")
        if not color.isValid():
            return
        self._custom_rgb = (color.redF(), color.greenF(), color.blueF())
        targets = self._targets()
        if not targets:
            self.lbl_status.setText("No hay nada seleccionado.")
            return
        done, skipped = apply_color(targets, rgb=self._custom_rgb)
        self._select_swatch(None)
        self._report(done, skipped, "RGB aplicado")


_ui_instance = None


def show():
    """Abre la ventana, cerrando cualquier instancia previa."""
    global _ui_instance
    if _ui_instance is not None:
        try:
            _ui_instance.close()
            _ui_instance.deleteLater()
        except RuntimeError:
            pass
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == WINDOW_OBJECT_NAME:
            widget.close()
            widget.deleteLater()

    _ui_instance = ColorOverrideUI()
    _ui_instance.show()
    return _ui_instance


if __name__ == "__main__":
    show()