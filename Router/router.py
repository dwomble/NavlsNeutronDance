import ast
import csv
import json
import os
from os import path
import re
import requests
from requests import Response
import subprocess
import sys
import tkinter.filedialog as filedialog
import webbrowser
from pathlib import Path
from semantic_version import Version # type: ignore
from time import sleep
from typing import TYPE_CHECKING

from .strings import hdrs, lbls
from .context import Context, Debug, catch_exceptions

DATA_DIR = 'data'

class Router():
    # Singleton pattern
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


    def __init__(self) -> None:
        # Only initialize if it's the first time
        if hasattr(self, '_initialized'): return

        self.update_available:bool = False
        self.roadtoriches:bool = False
        self.fleetcarrier:bool = False
        self.route:list = []
        self.ships:dict = {}
        self.bodies:str = ""

        self.system:str = ""
        self.ship:str = ''
        self.range:float = 32.0
        self.efficiency:int = 60
        self.supercharge_mult:int = 4
        self.offset:int = 0
        self.jumps_left:int = 0
        self.next_stop:str = ""

        self._load()
        self._initialized = True


    def update_ships(self, ship_id:str, max_jump_range:float) -> None:
        if ship_id == '': return

        self.ships[ship_id] = round(max_jump_range * 0.95, 2)
        Debug.logger.debug(f"Updated ship {ship_id} with max jump range {max_jump_range * 0.95} LY")
        self.save()


    def copy_waypoint(self) -> None:
        if sys.platform == "linux" or sys.platform == "linux2":
            command = subprocess.Popen(["echo", "-n", self.next_stop], stdout=subprocess.PIPE)
            subprocess.Popen(["xclip", "-selection", "c"], stdin=command.stdout)
        else:
            if not Context.ui.parent:
                Debug.logger.error("UI isn't initialized yet")
                return
            Context.ui.ctc(self.next_stop)


    def goto_next_waypoint(self) -> None:
        if self.offset < len(self.route) - 1:
            self.update_route(1)


    def goto_prev_waypoint(self) -> None:
        if self.offset > 0:
            self.update_route(-1)


    def update_route(self, direction:int = 1) -> None:
        if direction > 0:
            if self.route[self.offset][1] not in [None, "", []]:
                self.jumps_left -= int(self.route[self.offset][1])
            self.offset += 1
        else:
            self.offset -= 1
            if self.route[self.offset][1] not in [None, "", []]:
                self.jumps_left += int(self.route[self.offset][1])

        if self.offset >= len(self.route):
            self.next_stop = "End of the road!"
            Context.ui.update_display()
        else:
            self.next_stop = self.route[self.offset][0]
            self.update_bodies_text()

            Context.ui.update_display()
            self.copy_waypoint()
        self.save()


    def goto_changelog_page(self) -> None:
        return
        changelog_url = 'https://github.com/rinkulu/EDMC-SpanshRouterRE/blob/master/CHANGELOG.md#'
        changelog_url += self.spansh_updater.version.replace('.', '')
        webbrowser.open(changelog_url)


    def plot_file(self) -> None:
        ftypes = [
            ('All supported files', '*.csv *.txt'),
            ('CSV files', '*.csv'),
            ('Text files', '*.txt'),
        ]
        filename:str = filedialog.askopenfilename(filetypes=ftypes, initialdir=os.path.expanduser('~'))

        if len(filename) > 0:
            try:
                ftype_supported = False
                if filename.endswith(".csv"):
                    ftype_supported = True
                    self.plot_csv(filename)

                elif filename.endswith(".txt"):
                    ftype_supported = True
                    self.plot_edts(filename)

                if ftype_supported:
                    self.offset = 0
                    self.next_stop = self.route[0][0]
                    self.update_bodies_text()
                    self.copy_waypoint()
                    Context.ui.update_display()
                    self.save()
                else:
                    Context.ui.set_error("Unsupported file type")
            except Exception as e:
                Debug.logger.error("Failed to read user file, exception info:", exc_info=e)
                Context.ui.update_display(True)
                Context.ui.set_error("An error occured while reading the file.")


    def plot_csv(self, filepath: Path | str, clear_previous_route: bool = True):
        with open(filepath, 'r', encoding='utf-8-sig', newline='') as csvfile:
            self.roadtoriches = False
            self.fleetcarrier = False

            if clear_previous_route:
                self.clear_route()

            route_reader = csv.DictReader(csvfile)

            # Get column header names as string
            if not route_reader.fieldnames:
                Debug.logger.error(f"File {filepath} is empty or of unsupported format")
                return
            headerline:str = ','.join(route_reader.fieldnames)

            # Define the differnt internal formats based on the CSV header row
            internalbasicheader1 = "System Name"
            internalbasicheader2 = "System Name,Jumps"
            internalrichesheader = "System Name,Jumps,Body Name,Body Subtype"
            internalfleetcarrierheader = "System Name,Jumps,Restock Tritium"
            # Define the differnt import file formats based on the CSV header row
            neutronimportheader = "System Name,Distance To Arrival,Distance Remaining,Neutron Star,Jumps"
            road2richesimportheader = "System Name,Body Name,Body Subtype,Is Terraformable,Distance To Arrival,Estimated Scan Value,Estimated Mapping Value,Jumps"  # noqa: E501
            fleetcarrierimportheader = "System Name,Distance,Distance Remaining,Fuel Used,Icy Ring,Pristine,Restock Tritium"

            if (headerline == internalbasicheader1) or (headerline == internalbasicheader2) or (headerline == neutronimportheader):
                for row in route_reader:
                    if row not in (None, "", []):
                        self.route.append([
                            row[hdrs["system_name"]],
                            row.get(hdrs["jumps"], "")  # Jumps column is optional
                        ])
                        if row.get(hdrs["jumps"]):  # Jumps column is optional
                            self.jumps_left += int(row[hdrs["jumps"]])

            elif headerline == internalrichesheader:
                self.roadtoriches = True

                for row in route_reader:
                    if row not in (None, "", []):
                        # Convert string representations of lists to actual Lists
                        bodynames = ast.literal_eval(row[hdrs["body_name"]])
                        bodysubtypes = ast.literal_eval(row[hdrs["body_subtype"]])

                        self.route.append([
                            row[hdrs["system_name"]],
                            row[hdrs["jumps"]],
                            bodynames,
                            bodysubtypes
                        ])
                        self.jumps_left += int(row[hdrs["jumps"]])

            elif headerline == internalfleetcarrierheader:
                self.fleetcarrier = True

                for row in route_reader:
                    if row not in (None, "", []):
                        self.route.append([
                            row[hdrs["system_name"]],
                            row[hdrs["jumps"]],
                            row[hdrs["restock_tritium"]]
                        ])
                        self.jumps_left += int(row[hdrs["jumps"]])

            elif headerline == road2richesimportheader:
                self.roadtoriches = True

                bodynames:list = []
                bodysubtypes:list = []

                for row in route_reader:
                    bodyname:str = row[hdrs["body_name"]]
                    bodysubtype:str = row[hdrs["body_subtype"]]

                    # Update the current system with additional bodies from new CSV row
                    if len(self.route) > 0 and row[hdrs["system_name"]] == self.route[-1][0]:
                        self.route[-1][2].append(bodyname)
                        self.route[-1][3].append(bodysubtype)
                        continue

                    if row not in (None, "", []):
                        bodynames.append(bodyname)
                        bodysubtypes.append(bodysubtype)

                        self.route.append([
                            row[hdrs["system_name"]],
                            row[hdrs["jumps"]],
                            bodynames.copy(),
                            bodysubtypes.copy()
                        ])
                        # Clear bodies for next system
                        bodynames.clear()
                        bodysubtypes.clear()

                        self.jumps_left += int(row[hdrs["jumps"]])

            elif headerline == fleetcarrierimportheader:
                self.fleetcarrier = True

                for row in route_reader:
                    if row not in (None, "", []):
                        self.route.append([
                            row[hdrs["system_name"]],
                            1,  # Jumps is faked as every row is 1 jump
                            row[hdrs["restock_tritium"]]
                        ])
                        self.jumps_left += 1    # Jumps is faked as every row is 1 jump

            else:
                Context.ui.set_error("Could not detect file format")


    def plot_route(self, source:str, dest:str, efficiency:int, range:float, supercharge_mult:int = 4) -> bool:
        Debug.logger.debug(f"Plotting route")

        try:
            job_url = "https://spansh.co.uk/api/route?"

            results:Response = requests.post(job_url,
                params={"efficiency": efficiency, "range": range, "from": source, "to": dest, 'supercharge_multiplier': supercharge_mult},
                headers={'User-Agent': Context.plugin_useragent})

            if results.status_code != 202:
                self.plot_error(results)
                return False

            tries = 0
            while tries < 20:
                response:dict = json.loads(results.content)
                job:str = response["job"]

                results_url:str = "https://spansh.co.uk/api/results/" + job
                route_response:Response = requests.get(results_url, timeout=5)
                if route_response.status_code != 202:
                    break
                tries += 1
                sleep(1)

            if not route_response:
                Debug.logger.error("Query to Spansh timed out")
                Context.ui.set_error("The query to Spansh was too long and timed out, please try again.")

            if route_response.status_code != 200:
                self.plot_error(route_response)
                return False

            route:dict = json.loads(route_response.content)["result"]["system_jumps"]
            self.clear_route()
            for waypoint in route:
                self.route.append([waypoint["system"], str(waypoint["jumps"])])
                self.jumps_left += waypoint["jumps"]

            self.offset = 1 if self.route[0][0] == Context.system else 0
            self.next_stop = self.route[self.offset][0]
            self.copy_waypoint()
            self.save()
            return True

        except Exception as e:
            Debug.logger.error("Failed to plot route, exception info:", exc_info=e)
            Context.ui.enable_plot_gui(True)
            Context.ui.set_error(lbls["plot_error"])
        Debug.logger.debug(f"Done")
        return False


    def plot_error(self, response:Response) -> None:
        Debug.logger.error(f"Failed to query plotted route from Spansh (response code {response.status_code}): {response.text}")
        Context.ui.enable_plot_gui(True)
        failure:dict = json.loads(response.content)

        if response.status_code == 400 and "error" in failure:
            Context.ui.set_error(failure["error"])
            if "starting system" in failure["error"]:
                Context.ui.source_ac["fg"] = "red"
            if "finishing system" in failure["error"]:
                Context.ui.dest_ac["fg"] = "red"
        else:
            Context.ui.set_error(lbls["plot_error"])
        return


    def plot_edts(self, filename: Path | str) -> None:
        try:
            with open(filename, 'r') as txtfile:
                route_txt:list = txtfile.readlines()
                self.clear_route()
                for row in route_txt:
                    if row not in (None, "", []):
                        if row.lstrip().startswith('==='):
                            jumps = int(re.findall(r"\d+ jump", row)[0].rstrip(' jumps'))
                            self.jumps_left += jumps

                            system:str = row[row.find('>') + 1:]
                            if ',' in system:
                                systems:list = system.split(',')
                                for system in systems:
                                    self.route.append([system.strip(), jumps])
                                    jumps = 1
                                    self.jumps_left += jumps
                            else:
                                self.route.append([system.strip(), jumps])
        except Exception as e:
            Debug.logger.error("Failed to parse TXT route file, exception info:", exc_info=e)
            Context.ui.enable_plot_gui(True)
            Context.ui.set_error("An error occured while reading the file.")


    def export_route(self) -> None:
        if len(self.route) == 0:
            Debug.logger.debug("No route to export")
            return

        route_start:str = self.route[0][0]
        route_end:str = self.route[-1][0]
        route_name:str = f"{route_start} to {route_end}"
        Debug.logger.debug(f"Exporting route: {route_name}")

        ftypes:list = [('TCE Flight Plan files', '*.exp')]
        filename:str = filedialog.asksaveasfilename(filetypes=ftypes, initialdir=os.path.expanduser('~'), initialfile=f"{route_name}.exp")

        if len(filename) > 0:
            try:
                with open(filename, 'w') as csvfile:
                    for row in self.route:
                        csvfile.write(f"{route_name},{row[0]}\n")
            except Exception as e:
                Debug.logger.error("Failed to write route to the file, exception info:", exc_info=e)
                Context.ui.set_error("An error occured while writing the file.")


    def clear_route(self) -> None:
        self.offset = 0
        self.route = []
        self.next_waypoint:str = ""
        self.jumps_left = 0
        self.roadtoriches = False
        self.fleetcarrier = False

        Context.ui.update_display()
        self.save()


    def save_route(self) -> None:
        save_route_path:Path = Context.plugin_dir / 'route.csv'

        if len(self.route) != 0:
            with open(save_route_path, 'w', newline='') as csvfile:
                if self.roadtoriches:
                    # Write output: System, Jumps, Bodies[], BodySubTypes[]
                    fieldnames:list = [hdrs["system_name"], hdrs["jumps"], hdrs["body_name"], hdrs["body_subtype"]]
                    writer = csv.writer(csvfile)
                    writer.writerow(fieldnames)
                    for row in self.route:
                        writer.writerow(row)

                if self.fleetcarrier:
                    # Write output: System, Jumps,
                    fieldnames = [hdrs["system_name"], hdrs["jumps"], hdrs["restock_tritium"]]
                    writer = csv.writer(csvfile)
                    writer.writerow(fieldnames)
                    for row in self.route:
                        writer.writerow(row)

                else:
                    # Write output: System, Jumps
                    fieldnames = [hdrs["system_name"], hdrs["jumps"]]
                    writer = csv.writer(csvfile)
                    writer.writerow(fieldnames)
                    writer.writerows(self.route)
        else:
            try:
                os.remove(save_route_path)
            except Exception:
                Debug.logger.debug("No route to delete")


    def update_bodies_text(self) -> None:
        if not self.roadtoriches:
            return

        # For the bodies to scan use the current system, which is one before the next stop
        lastsystemoffset:int = self.offset - 1
        if lastsystemoffset < 0:
            lastsystemoffset = 0    # Display bodies of the first system

        lastsystem:str = self.route[lastsystemoffset][0]
        bodynames:str = self.route[lastsystemoffset][2]
        bodysubtypes:str = self.route[lastsystemoffset][3]

        waterbodies:list = []
        rockybodies:list = []
        metalbodies:list = []
        earthlikebodies:list = []
        unknownbodies:list = []

        for num, name in enumerate(bodysubtypes):
            shortbodyname:str = bodynames[num].replace(lastsystem + " ", "")
            if name.lower() == "high metal content world":
                metalbodies.append(shortbodyname)
            elif name.lower() == "rocky body":
                rockybodies.append(shortbodyname)
            elif name.lower() == "earth-like world":
                earthlikebodies.append(shortbodyname)
            elif name.lower() == "water world":
                waterbodies.append(shortbodyname)
            else:
                unknownbodies.append(shortbodyname)

        bodysubtypeandname:str = ""
        if len(metalbodies) > 0:
            bodysubtypeandname += "\n   Metal: " + ', '.join(metalbodies)
        if len(rockybodies) > 0:
            bodysubtypeandname += "\n   Rocky: " + ', '.join(rockybodies)
        if len(earthlikebodies) > 0:
            bodysubtypeandname += "\n   Earth: " + ', '.join(earthlikebodies)
        if len(waterbodies) > 0:
            bodysubtypeandname += "\n   Water: " + ', '.join(waterbodies)
        if len(unknownbodies) > 0:
            bodysubtypeandname += "\n   Unknown: " + ', '.join(unknownbodies)

        self.bodies = f"\n{lastsystem}:{bodysubtypeandname}"


    def check_for_update(self) -> None:
        return
        version_url = "https://raw.githubusercontent.com/rinkulu/EDMC-SpanshRouterRE/master/version"
        try:
            response = requests.get(version_url, timeout=2)
            if response.status_code == 200:
                if Context.plugin_version != Version(response.text):
                    self.update_available = True
                    self.spansh_updater = Updater(response.text, Context.plugin_dir)
            else:
                Debug.logger.error(
                    f"Could not query latest SpanshRouterRE version (status code {response.status_code}): "
                    + response.text
                )
        except Exception as e:
            Debug.logger.error("Failed to check for updates, exception info:", exc_info=e)

    def install_update(self) -> None:
        return
        self.spansh_updater.install()

    @catch_exceptions
    def _load(self) -> None:
        ''' Load state from file '''
        file:str = path.join(Context.plugin_dir, DATA_DIR, 'route.json')
        if path.exists(file):
            with open(file) as json_file:
                self._from_dict(json.load(json_file))


    @catch_exceptions
    def save(self) -> None:
        ''' Save state to file '''

        ind:int = 4
        file:str = path.join(Context.plugin_dir, DATA_DIR, 'route.json')
        with open(file, 'w') as outfile:
            json.dump(self._as_dict(), outfile, indent=ind)


    def _as_dict(self) -> dict:
        ''' Return a Dictionary representation of our data, suitable for serializing '''

        return {
            'system': self.system,
            'range': self.range,
            'efficiency': self.efficiency,
            'supercharge_mult': self.supercharge_mult,
            'offset': self.offset,
            'jumps_left': self.jumps_left,
            'next_stop': self.next_stop,
            'route': self.route,
            'ships': self.ships
            }


    def _from_dict(self, dict:dict) -> None:
        ''' Populate our data from a Dictionary that has been deserialized '''
        self.system = dict.get('system', '')
        self.range = dict.get('range', 32.0)
        self.efficiency = dict.get('efficiency', 60)
        self.supercharge_mult = dict.get('supercharge_mult', 4)
        self.offset = dict.get('offset', 0)
        self.jumps_left = dict.get('jumps_left', 0)
        self.next_stop = dict.get('next_stop', "")
        self.route = dict.get('route', [])
        self.ships = dict.get('ships', {})
