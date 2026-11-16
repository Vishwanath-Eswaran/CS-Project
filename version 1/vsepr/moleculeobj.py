
try:
    from .element import atom
except ImportError:  # pragma: no cover - direct script execution fallback
    from element import atom

from math import asin, cos, pi, sin
from vpython import color, compound, cross, cylinder, mag, norm, sphere, vector

class molecule:
    """Build the atom objects and 3D shapes for one molecule."""

    def __init__(self,struc:dict): 
        """Read the structure map and make the molecule's atoms and shapes."""
        # Make one atom object for each unique atom label in the structure.
        atms=[] 
        atmobj = {} 
        for i in list(struc.values())+[list(struc.keys())]: 
            for j in i: 
                if j not in atms: 
                    n='' 
                    for k in j: 
                        if k.isalpha(): 
                            n+=k 
                    atmobj[j] = atom(n,j) 
                    atms.append(j) 
        # Keep the atom objects and structure so the other methods can use them.
        self.atms=atms 
        self.atmobj = atmobj 
        self.struc = struc 
        self.cyclic = False
        self.attachatms() 
        self.checkcycle()
        if self.cyclic:
            self.gencyclic()
        else:
            self.genstchain()
        self.disturb()
     
    def attachatms(self): 
        """Connect each atom to the atoms listed beside it in the structure."""
        # Add every listed connection to both atoms when needed.
        struct = self.struc 
        atmobj = self.atmobj 
        for (k,v) in struct.items(): 
            for i in v: 
                atmobj[k].attach(atmobj[i]) 
                if i not in struct.keys(): 
                    atmobj[i].attach(atmobj[k]) 
    @staticmethod
    def hex_to_rgb(hex_color):
        """Change a color like #FF0000 into a VPython color value."""
        # Read each pair of hex digits and scale its color value from 0 to 1.
        hex_color = hex_color.lstrip("#")
        return vector(
            int(hex_color[0:2], 16) / 255,
            int(hex_color[2:4], 16) / 255,
            int(hex_color[4:6], 16) / 255
        )
    def genstchain(self):
        """Create and assign spheres for a non-cyclic molecule."""
        self._make_spheres({})

    @staticmethod
    def _bond_directions(atom_count):
        """Start attached groups in a plane so repulsion can spread them out."""
        if atom_count == 0:
            return []
        return [
            vector(
                0,
                cos(2 * pi * index / atom_count),
                sin(2 * pi * index / atom_count),
            )
            for index in range(atom_count)
        ]

    def _make_spheres(self, center_positions):
        """Create center and attached atom spheres at the supplied positions."""
        struct = self.struc
        atmobj = self.atmobj
        atmballs = {}
        center_atoms = [atmobj[label] for label in struct]
        center_labels = list(struct)
        center_positions = center_positions.copy()

        center_label_set = set(center_labels)
        placed_new_center = True
        while placed_new_center:
            placed_new_center = False
            for parent_label in center_labels:
                if parent_label not in center_positions:
                    continue
                children = []
                for attached in atmobj[parent_label].attached:
                    if (
                        attached.name in center_label_set
                        and attached.name not in center_positions
                        and attached.name not in children
                    ):
                        children.append(attached.name)
                if not children:
                    continue

                parent_position = center_positions[parent_label]
                outward = norm(vector(parent_position.x, parent_position.y, 0))
                if mag(outward) == 0:
                    outward = vector(1, 0, 0)
                angle_step = 2 * pi / 3
                for index, label in enumerate(children):
                    angle = (index - (len(children) - 1) / 2) * angle_step
                    direction = vector(
                        outward.x * cos(angle) - outward.y * sin(angle),
                        outward.x * sin(angle) + outward.y * cos(angle),
                        0,
                    )
                    distance = atmobj[label].rad + atmobj[parent_label].rad
                    center_positions[label] = (
                        parent_position + direction * distance
                    )
                    placed_new_center = True

        n = 0

        for index, cenatm in enumerate(center_labels):
            position = center_positions.get(cenatm, vector(n, 0, 0))
            cenball = sphere(
                radius=atmobj[cenatm].rad / 1.5,
                pos=position,
                color=self.hex_to_rgb(atmobj[cenatm].color),
            )
            atmobj[cenatm].ball = cenball
            if index + 1 < len(center_labels):
                next_center = center_labels[index + 1]
                if atmobj[next_center] in atmobj[cenatm].attached:
                    n += atmobj[cenatm].rad + atmobj[next_center].rad
                else:
                    n += 30

        for cenatm in center_labels:
            attball = []
            attached_atoms = []
            for attached in atmobj[cenatm].attached:
                if attached.name not in [atom.name for atom in attached_atoms]:
                    attached_atoms.append(attached)
            directions = self._bond_directions(len(attached_atoms))

            for index, atm in enumerate(attached_atoms):
                if atm not in center_atoms:
                    distance = atmobj[cenatm].rad + atm.rad
                    if self.cyclic and cenatm in self.cycle and atm.symbol != "lp":
                        center_position = atmobj[cenatm].ball.pos
                        outward = norm(
                            vector(center_position.x, center_position.y, 0)
                        )
                        pos = center_position + outward * distance
                    else:
                        direction = directions[index] if directions else vector(
                            0,
                            cos(index * 2 * pi / len(attached_atoms)),
                            sin(index * 2 * pi / len(attached_atoms)),
                        )
                        pos = atmobj[cenatm].ball.pos + direction * distance
                    if atm.symbol == "lp":
                        color = self.hex_to_rgb(atm.color)
                        shell = sphere(
                            radius=atm.rad * 0.8,
                            pos=pos,
                            color=color,
                            opacity=0.25,
                        )
                        electron1 = sphere(
                            radius=atm.rad * 0.2,
                            pos=pos + vector(-atm.rad * 0.3, 0, 0),
                            color=color,
                        )
                        electron2 = sphere(
                            radius=atm.rad * 0.2,
                            pos=pos + vector(atm.rad * 0.3, 0, 0),
                            color=color,
                        )
                        ball = compound([shell, electron1, electron2])
                    else:
                        ball = sphere(
                            radius=atm.rad / 2,
                            pos=pos,
                            color=self.hex_to_rgb(atm.color),
                        )
                    attball.append(ball)
                    atm.ball = ball
            atmballs[atmobj[cenatm].ball] = attball

        self.atmballs = atmballs

    def cylinders(self):
        """Create parallel cylinders to show each real-atom bond order."""
        self.bond_cylinders = []
        seen_bonds = set()

        for label, neighbors in self.struc.items():
            for neighbor in neighbors:
                first = self.atmobj[label]
                second = self.atmobj[neighbor]
                if first.symbol == "lp" or second.symbol == "lp":
                    continue

                pair = tuple(sorted((label, neighbor)))
                if pair in seen_bonds:
                    continue
                seen_bonds.add(pair)

                order = max(
                    neighbors.count(neighbor),
                    self.struc.get(neighbor, []).count(label),
                )
                spacing = min(first.rad, second.rad) * 0.3
                for index in range(order):
                    offset = (index - (order - 1) / 2) * spacing
                    bond = cylinder(
                        pos=first.ball.pos,
                        axis=second.ball.pos - first.ball.pos,
                        radius=min(first.rad, second.rad) * 0.08,
                        color=color.gray(0.7),
                    )
                    self.bond_cylinders.append(
                        (bond, first, second, offset)
                    )

        return self.bond_cylinders

    def checkcycle(self):
        """Find the first ring by following bonds between center atoms."""
        center_labels = set(self.struc)
        visited = set()
        path = []
        self.cycle = []

        def find_cycle(current, parent=None):
            visited.add(current)
            path.append(current)
            neighbors = {
                atom.name
                for atom in self.atmobj[current].attached
                if atom.name in center_labels
            }
            for neighbor in neighbors:
                if neighbor == parent:
                    continue
                if neighbor in visited:
                    cycle_start = path.index(neighbor)
                    if len(path) - cycle_start >= 3:
                        self.cycle = path[cycle_start:].copy()
                        return True
                elif find_cycle(neighbor, current):
                    return True
            path.pop()
            return False

        for label in self.struc:
            if label not in visited and find_cycle(label):
                break

        self.cyclic = bool(self.cycle)

    def gencyclic(self):
        """Create and assign the spheres, placing the detected ring on a circle."""
        if not self.cycle:
            self.genstchain()
            return

        bond_lengths = []
        for index, label in enumerate(self.cycle):
            next_label = self.cycle[(index + 1) % len(self.cycle)]
            bond_lengths.append(
                self.atmobj[label].rad + self.atmobj[next_label].rad
            )

        # A chord of length d in a circle of radius R has angle
        # 2 * asin(d / (2 * R)). Choose R so all ring angles total 2*pi.
        low = max(bond_lengths) / 2

        def angle_sum(radius):
            return sum(
                2 * asin(length / (2 * radius))
                for length in bond_lengths
            )

        if angle_sum(low) < 2 * pi:
            raise ValueError("The ring bond lengths cannot form a circle.")

        high = max(low * 2, 1)
        while angle_sum(high) > 2 * pi:
            high *= 2

        for _ in range(60):
            radius = (low + high) / 2
            if angle_sum(radius) > 2 * pi:
                low = radius
            else:
                high = radius

        radius = (low + high) / 2
        positions = {}
        angle = 0
        for index, label in enumerate(self.cycle):
            positions[label] = vector(
                radius * cos(angle),
                radius * sin(angle),
                0,
            )
            angle += 2 * asin(bond_lengths[index] / (2 * radius))
        self._make_spheres(positions)
    def disturb(self):
        """Give flat groups a small out-of-plane offset to start repulsion."""
        center_labels = set(self.struc)
        for center_label in self.struc:
            center = self.atmobj[center_label]
            attached_atoms = []
            for attached in center.attached:
                if (
                    attached.name not in center_labels
                    and attached.name not in [atom.name for atom in attached_atoms]
                ):
                    attached_atoms.append(attached)

            bond_vectors = [
                attached.ball.pos - center.ball.pos
                for attached in attached_atoms
            ]
            plane_normal = vector(0, 0, 0)
            for first_index in range(len(bond_vectors)):
                for second_index in range(first_index + 1, len(bond_vectors)):
                    plane_normal = cross(
                        bond_vectors[first_index],
                        bond_vectors[second_index],
                    )
                    if mag(plane_normal) > 0.001:
                        break
                if mag(plane_normal) > 0.001:
                    break
            if mag(plane_normal) == 0:
                continue
            plane_normal = norm(plane_normal)

            for index, attached in enumerate(attached_atoms):
                bond_length = center.rad + attached.rad
                sign = 1 if index % 2 == 0 else -1
                offset = min(5, bond_length * 0.05) * sign
                new_direction = norm(
                    bond_vectors[index] + plane_normal * offset
                )
                attached.ball.pos = center.ball.pos + new_direction * bond_length
