# -*- coding: utf-8 -*-
"""
lra_tool.py
------------------------------------------------------------
Mostrar / ocultar los Local Rotation Axis (LRA) de los nodos de
Maya, con dos modos de alcance:

  1) Selection  -- solo los nodos seleccionados.
  2) Hierarchy  -- los seleccionados y TODOS sus descendientes.

Extras utiles:
  - Filtro "Joints only" para no llenar el viewport de ejes de
    controles, grupos y geometria cuando trabajas una cadena.
  - "Hide All in Scene": apaga los LRA de toda la escena, para
    cuando ya no sabes cuales dejaste encendidos.

Por debajo esto toca el atributo 'displayLocalAxis', que existe
en cualquier transform (joints incluidos). Los nodos cuyo
atributo este bloqueado o conectado se saltan con un aviso en
vez de reventar a mitad de la operacion.

Uso con UI:
    import importlib
    import lra_tool
    importlib.reload(lra_tool)
    lra_tool.show()

Uso directo (util para hotkeys):
    import lra_tool
    lra_tool.show_axis(hierarchy=True)     # mostrar en jerarquia
    lra_tool.hide_axis()                   # ocultar en la seleccion
    lra_tool.toggle_axis(hierarchy=True)
    lra_tool.hide_all_in_scene()
------------------------------------------------------------
"""

import maya.cmds as cmds

WINDOW_NAME = "lraToolWindow"
ATTR = "displayLocalAxis"

# Referencias a los controles de la UI
_UI = {}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _resolve_transforms(nodes):
    """Convierte lo que sea que venga (transforms, shapes, componentes
    tipo vertices/caras, joints) en la lista de transforms sobre los que
    tiene sentido activar el LRA."""
    result = []
    for node in (nodes or []):
        # componentes -> su objeto; ej: pCube1.vtx[3] -> pCube1
        obj = node.split(".")[0]
        if not cmds.objExists(obj):
            continue
        if cmds.objectType(obj, isAType="transform"):
            result.append(obj)
        else:
            # shapes (mesh, nurbsCurve, camera...) -> su transform padre
            parents = cmds.listRelatives(obj, parent=True, fullPath=True) or []
            if parents:
                result.append(parents[0])
    # dedup manteniendo el orden de seleccion
    seen = set()
    unique = []
    for node in result:
        key = cmds.ls(node, long=True)[0]
        if key not in seen:
            seen.add(key)
            unique.append(node)
    return unique


def _expand_hierarchy(nodes):
    """Añade a la lista todos los descendientes tipo transform."""
    expanded = list(nodes)
    for node in nodes:
        children = cmds.listRelatives(
            node, allDescendents=True, type="transform", fullPath=True
        ) or []
        expanded.extend(children)
    seen = set()
    unique = []
    for node in expanded:
        key = cmds.ls(node, long=True)[0]
        if key not in seen:
            seen.add(key)
            unique.append(node)
    return unique


def _filter_joints(nodes):
    return [n for n in nodes if cmds.nodeType(n) == "joint"]


def _collect_nodes(nodes=None, hierarchy=False, joints_only=False):
    """Lista final de nodos sobre los que operar, a partir de la
    seleccion (o de 'nodes' si se pasa explicitamente)."""
    if nodes is None:
        nodes = cmds.ls(selection=True, long=True) or []
    targets = _resolve_transforms(nodes)
    if hierarchy:
        targets = _expand_hierarchy(targets)
    if joints_only:
        targets = _filter_joints(targets)
    return targets


def _set_attr_safe(node, value):
    """Devuelve True si se aplico, False si el atributo no existe, esta
    bloqueado o viene conectado desde otro sitio."""
    attr = "{}.{}".format(node, ATTR)
    if not cmds.objExists(attr):
        return False
    try:
        if cmds.getAttr(attr, lock=True):
            return False
        if cmds.connectionInfo(attr, isDestination=True):
            return False
        cmds.setAttr(attr, bool(value))
        return True
    except Exception:
        return False


def _apply(value, nodes=None, hierarchy=False, joints_only=False):
    targets = _collect_nodes(nodes, hierarchy, joints_only)
    if not targets:
        cmds.warning(
            "No hay nodos validos. Selecciona algo en el viewport o el Outliner"
            + (" (con 'Joints only' activo solo se cuentan joints)." if joints_only else ".")
        )
        return 0, 0

    done = 0
    skipped = []
    for node in targets:
        if _set_attr_safe(node, value):
            done += 1
        else:
            skipped.append(node)

    if skipped:
        cmds.warning(
            "{} nodo(s) saltados (atributo bloqueado, conectado o inexistente): {}".format(
                len(skipped), ", ".join(skipped[:5]) + (" ..." if len(skipped) > 5 else "")
            )
        )
    return done, len(skipped)


def _feedback(message):
    """Mensaje discreto en el viewport en vez de un dialogo modal."""
    try:
        cmds.inViewMessage(assistMessage=message, position="midCenterBot", fade=True)
    except Exception:
        pass
    print(message)


# ------------------------------------------------------------------
# API publica
# ------------------------------------------------------------------
def show_axis(nodes=None, hierarchy=False, joints_only=False):
    done, _ = _apply(True, nodes, hierarchy, joints_only)
    if done:
        _feedback("LRA visible en {} nodo(s).".format(done))
    return done


def hide_axis(nodes=None, hierarchy=False, joints_only=False):
    done, _ = _apply(False, nodes, hierarchy, joints_only)
    if done:
        _feedback("LRA oculto en {} nodo(s).".format(done))
    return done


def toggle_axis(nodes=None, hierarchy=False, joints_only=False):
    """El estado del PRIMER nodo manda: si lo tiene visible, se apaga
    todo el grupo, y al reves. Asi el toggle es predecible en cadenas
    donde algunos nodos estan encendidos y otros no."""
    targets = _collect_nodes(nodes, hierarchy, joints_only)
    if not targets:
        cmds.warning("No hay nodos validos. Selecciona algo primero.")
        return 0

    current = False
    for node in targets:
        attr = "{}.{}".format(node, ATTR)
        if cmds.objExists(attr):
            try:
                current = bool(cmds.getAttr(attr))
                break
            except Exception:
                continue

    done, _ = _apply(not current, targets, hierarchy=False, joints_only=False)
    if done:
        _feedback("LRA {} en {} nodo(s).".format(
            "oculto" if current else "visible", done))
    return done


def hide_all_in_scene():
    """Apaga el LRA en todos los transforms de la escena."""
    all_transforms = cmds.ls(type="transform", long=True) or []
    done = 0
    for node in all_transforms:
        attr = "{}.{}".format(node, ATTR)
        try:
            if cmds.objExists(attr) and cmds.getAttr(attr):
                if _set_attr_safe(node, False):
                    done += 1
        except Exception:
            continue
    _feedback("LRA oculto en {} nodo(s) de la escena.".format(done))
    return done


def select_visible_in_scene():
    """Selecciona los nodos que tienen el LRA encendido, para poder
    revisarlos antes de apagarlos en masa."""
    found = []
    for node in (cmds.ls(type="transform", long=True) or []):
        attr = "{}.{}".format(node, ATTR)
        try:
            if cmds.objExists(attr) and cmds.getAttr(attr):
                found.append(node)
        except Exception:
            continue
    if found:
        cmds.select(found, replace=True)
        _feedback("{} nodo(s) con LRA visible.".format(len(found)))
    else:
        cmds.select(clear=True)
        _feedback("Ningun nodo tiene el LRA visible.")
    return found


# ------------------------------------------------------------------
# UI
# ------------------------------------------------------------------
def _scope_hierarchy():
    ctrl = _UI.get("scope")
    if not ctrl or not cmds.radioButtonGrp(ctrl, exists=True):
        return False
    return cmds.radioButtonGrp(ctrl, query=True, select=True) == 2


def _joints_only():
    ctrl = _UI.get("jointsOnly")
    if not ctrl or not cmds.checkBox(ctrl, exists=True):
        return False
    return cmds.checkBox(ctrl, query=True, value=True)


def _run(func):
    func(hierarchy=_scope_hierarchy(), joints_only=_joints_only())


def show():
    global _UI
    _UI = {}

    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    window = cmds.window(WINDOW_NAME, title="LOCAL ROTATION AXIS",
                          widthHeight=(330, 260), sizeable=True)

    main = cmds.columnLayout(parent=window, adjustableColumn=True,
                              rowSpacing=6, columnAttach=("both", 12))

    cmds.separator(height=6, style="none")
    cmds.text(label="Scope", align="left", font="boldLabelFont")
    _UI["scope"] = cmds.radioButtonGrp(
        numberOfRadioButtons=2,
        labelArray2=("Selection", "Hierarchy"),
        columnWidth2=(130, 150),
        select=1,
    )
    _UI["jointsOnly"] = cmds.checkBox(label="Joints only", value=False)

    cmds.separator(height=10, style="in")

    cmds.button(label="Show LRA", height=32,
                backgroundColor=(0.25, 0.45, 0.25),
                command=lambda *_: _run(show_axis))
    cmds.button(label="Hide LRA", height=32,
                backgroundColor=(0.45, 0.28, 0.28),
                command=lambda *_: _run(hide_axis))
    cmds.button(label="Toggle LRA", height=28,
                command=lambda *_: _run(toggle_axis))

    cmds.separator(height=10, style="in")
    cmds.text(label="Scene", align="left", font="boldLabelFont")
    cmds.button(label="Select Nodes with LRA Visible", height=26,
                command=lambda *_: select_visible_in_scene())
    cmds.button(label="Hide All in Scene", height=26,
                command=lambda *_: hide_all_in_scene())
    cmds.separator(height=8, style="none")

    cmds.setParent(main)
    cmds.showWindow(window)


if __name__ == "__main__":
    show()