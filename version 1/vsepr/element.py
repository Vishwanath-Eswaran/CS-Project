import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_elements():
    """Read element details from elements.csv into a symbol-based dictionary."""
    elements = {}
    csv_path = DATA_DIR / "elements.csv"
    with open(csv_path, "r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            symbol = row["symbol"]
            elements[symbol] = {
                "atomic_number": int(row["atomic_number"]),
                "name": row["name"],
                "covalent_radius_pm": float(row["covalent_radius_pm"]),
                "atomic_mass": float(row["atomic_mass"]),
                "electronegativity_pauling": (
                    float(row["electronegativity_pauling"])
                    if row["electronegativity_pauling"]
                    else None
                ),
                "color": row["color"],
                "valence_electrons": int(row["valence_electrons"]),
                "allowed_valences": tuple(
                    int(value)
                    for value in row["allowed_valences"].split(";")
                ),
            }
    return elements


ELEMENTS_BY_SYMBOL = load_elements()


class atom: 
    """Store the details and movement data for one atom."""

    def __init__(self,symbol,name): 
        """Set this atom's element data, color, and starting movement values."""
        import vpython

        self.name = name 
        self.symbol=symbol 
        # Give a lone pair its own display values instead of looking it up in the CSV.
        if symbol == "lp":
            self.atmno = 0
            self.rad = 10
            self.mass = 1
            self.elecneg = 0
            self.color = "#800080"
        else:
            # Find this element's information in the CSV data loaded above.
            try:
                element_data = ELEMENTS_BY_SYMBOL[symbol]
            except KeyError:
                raise ValueError("Unknown element symbol: " + symbol)
            self.atmno = element_data["atomic_number"]
            self.rad = element_data["covalent_radius_pm"]
            self.mass = element_data["atomic_mass"]
            self.elecneg = element_data["electronegativity_pauling"]
            self.color = element_data["color"]
            self.valence_electrons = element_data["valence_electrons"]
            self.allowed_valences = element_data["allowed_valences"]
        # Set the starting movement, attachments, display shape, and force.
        self.velocity = vpython.vector(0,0,0) 
        self.attached = [] 
        self.ball = None 
        self.force=vpython.vector(0,0,0)
    def attach(self,atom): 
        """Add another atom to this atom's list of attached atoms."""
        # Remember which atom is connected to this one.
        self.attached.append(atom) 