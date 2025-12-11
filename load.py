import logging
import os
import tkinter as tk
import tkinter.messagebox as confirmDialog
from pathlib import Path
from semantic_version import Version #type: ignore

from config import appname  # type: ignore

from Router.context import Context, Debug, catch_exceptions
from Router.router import Router
from Router.ui import UI

NAME="Navl's Neutron Dancer"

@catch_exceptions
def plugin_start3(plugin_dir: str) -> str:
    # Debug Class
    Debug(plugin_dir)
    Context.plugin_name = NAME
    Context.plugin_dir = Path(plugin_dir).resolve()
    version_file = Context.plugin_dir / "version"
    Context.plugin_version = Version(version_file.read_text())
    Context.plugin_useragent = f"EDMC-{NAME}-{Context.plugin_version}"
    Debug.logger.info(f"Starting (start3) {NAME} version {Context.plugin_version} in {appname}")
    #Context.router.check_for_update()
    return NAME

@catch_exceptions
def plugin_start(plugin_dir: str) -> None:
    """EDMC calls this function when running in Python 2 mode."""
    raise EnvironmentError("This plugin requires EDMC version 4.0 or later.")

@catch_exceptions
def plugin_stop() -> None:
    Context.router.save()
    if Context.router.update_available:
        Context.router.install_update()

@catch_exceptions
def journal_entry(cmdr:str, is_beta:bool, system:str, station:str, entry:dict, state:dict) -> None:
    sys:str = entry.get('StarSystem', system)
    Debug.logger.debug(f"Journal Entry: {entry['event']} in {sys} ({Context.router.system}")
    if sys != Context.router.system:
        Context.router.system = sys
        Context.router.update_route()

    match entry['event']:
        case 'Loadout':
            Context.router.set_ship(entry.get('ShipID', ''), entry.get('MaxJumpRange', 0.0), entry.get('ShipName', ''), entry.get('Ship', ''))


@catch_exceptions
def ask_for_update() -> None:
    if Context.router.update_available:
        update_txt = "Update available!\n"
        update_txt += "If you choose to install it, you will have to restart EDMC for it to take effect.\n\n"
        #update_txt += Context.router.spansh_updater.changelogs
        update_txt += "\n\nInstall?"
        install_update = confirmDialog.askyesno("SpanshRouterRedux", update_txt)

        if install_update:
            confirmDialog.showinfo("SpanshRouterRedux", "The update will be installed as soon as you quit EDMC.")
        else:
            Context.router.update_available = False

@catch_exceptions
def plugin_app(parent:tk.Widget) -> tk.Frame:
    Context.router = Router()
    Context.ui = UI(parent)
    Context.ui.update_display(True)

    parent.master.after_idle(ask_for_update)
    return Context.ui.frame
