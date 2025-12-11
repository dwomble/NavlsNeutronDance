import ast
import csv
import os
from pathlib import Path
from tkinter import filedialog
import re

from utils.Debug import Debug, catch_exceptions
from .context import Context

# Headers that we accept
HEADERS:list = ["System Name", "Jumps", "Neutron Star", "Body Name", "Body Subtype",
                "Is Terraformable", "Distance To Arrival", "Estimated Scan Value", "Estimated Mapping Value",
                "Distance", "Distance Jumped", "Distance Remaining", "Fuel Used", "Icy Ring", "Pristine", "Restock Tritium"]

class csv_handler:
    """ Handle csv import/export, not currently used """

    @catch_exceptions
    def import_csv(self, filepath:Path|str, clear_previous_route:bool = True):
        """ Import a csv file """
        ftypes = [
            ('All supported files', '*.csv *.txt'),
            ('CSV files', '*.csv'),
            ('Text files', '*.txt'),
        ]
        filename:str = filedialog.askopenfilename(filetypes=ftypes, initialdir=os.path.expanduser('~'))

        if len(filename) == 0:
            Debug.logger.debug(f"No filename selected")
            return

        with open(filepath, 'r', encoding='utf-8-sig', newline='') as csvfile:
            self.roadtoriches = False
            self.fleetcarrier = False

            if clear_previous_route:
                Context.router.clear_route()

            route_reader = csv.DictReader(csvfile)
            # Check it has column headings
            if not route_reader.fieldnames:
                Debug.logger.error(f"File {filepath} is empty or does't have a header row")
                return

            hdrs:list = list(set(HEADERS).intersection(set(route_reader.fieldnames)))
            if hdrs == [] or "System Name" not in hdrs:
                Debug.logger.error(f"File {filepath} is of unsupported format")
                return

            route:list = []
            for row in route_reader:
                r:list = []
                if row not in (None, "", []): continue
                for col in hdrs:
                    if col in row:
                        if col in ["body_name", "body_subtype"]:
                            r.append(ast.literal_eval(row[col]))
                            continue
                        m = re.match(r"^\d+(\.\d+)?$", row[col])
                        Debug.logger.debug(f"Row {row[col]} {m}")
                        r.append(row[col] if not re.match(r"^\d+(\.\d+)?$", row[col]) else round(float(row[col]), 2))
                route.append(r)

            self.fleetcarrier = True if "Fuel Used" in hdrs else False
            self.roadtoriches = True if "Estimated Scan Value" in hdrs else False
            Debug.logger.debug(f"Headers: {hdrs} rows {len(route)}")
            self.headers = hdrs
            self.route = route


    def export_route(self) -> None:
        """ Export the route as a csv """

        if self.route == [] or self.headers == []:
            Debug.logger.debug(f"No route")
            return

        route_start:str = self.route[0][0]
        route_end:str = self.route[-1][0]
        route_name:str = f"{route_start} to {route_end}"
        ftypes:list = [('CSV files', '*.csv')]
        filename:str = filedialog.asksaveasfilename(filetypes=ftypes, initialdir=os.path.expanduser('~'), initialfile=f"{route_name}.csv")

        if len(filename) == 0:
            Debug.logger.debug(f"No filename selected")
            return

        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(self.headers)
            for row in self.route:
                writer.writerow(row)


    def update_bodies_text(self) -> None:
        if not self.roadtoriches:
            return

        # For the bodies to scan use the current system, which is one before the next stop
        lastsystemoffset:int = Context.router.offset - 1
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