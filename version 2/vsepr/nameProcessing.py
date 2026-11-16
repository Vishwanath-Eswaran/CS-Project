import pickle
import re
import sys
from pathlib import Path

import pubchempy as pcp

try:
    from .element import ELEMENTS_BY_SYMBOL
except ImportError:  # pragma: no cover - direct script execution fallback
    from element import ELEMENTS_BY_SYMBOL

PROJECT_DIR = Path(__file__).resolve().parent.parent


def _resolve_data_path(filename):
    """Return a path relative to this module so the project works from any CWD."""
    if filename is None:
        return PROJECT_DIR / "data" / "molecule.dat"

    path = Path(filename)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path


def load_molecule_map(filename=None):
    """Load the saved molecule structures from the local binary cache."""
    path = _resolve_data_path(filename)
    try:
        with open(path, "rb") as binary_file:
            saved_data = pickle.load(binary_file)
    except FileNotFoundError:
        return {}

    # New files store each molecule under the name or ID used to find it.
    if (
        isinstance(saved_data, dict)
        and saved_data.get("format") == "molecule-cache-v1"
        and isinstance(saved_data.get("molecules"), dict)
    ):
        return saved_data["molecules"]

    # The old file had no name, but the project's existing saved structure is propane.
    if isinstance(saved_data, dict) and saved_data:
        return {"propane": saved_data}
    return {}


def save_molecule_map(molecules, filename=None):
    """Save all named molecule structures to the local binary cache."""
    path = _resolve_data_path(filename)
    saved_data = {"format": "molecule-cache-v1", "molecules": molecules}
    with open(path, "wb") as binary_file:
        pickle.dump(saved_data, binary_file, protocol=4)


def carbon_map_from_smiles(smiles):
    """Turn a SMILES string into atoms and the atoms attached to each one."""
    atoms = []
    branches = []
    rings = {}
    current_atom = None
    pending_bond = None
    index = 0

    def add_atom(symbol, aromatic=False, charge=0, explicit_hydrogens=0):
        nonlocal current_atom, pending_bond
        if symbol not in ELEMENTS_BY_SYMBOL:
            raise ValueError("Unknown element symbol in SMILES: " + symbol)
        atom_index = len(atoms)
        atoms.append({
            "symbol": symbol,
            "aromatic": aromatic,
            "charge": charge,
            "explicit_hydrogens": explicit_hydrogens,
            "bonds": [],
        })
        if current_atom is not None:
            order = pending_bond
            if order is None:
                order = (
                    1.5
                    if atoms[current_atom]["aromatic"] and aromatic
                    else 1
                )
            atoms[current_atom]["bonds"].append((atom_index, order))
            atoms[atom_index]["bonds"].append((current_atom, order))
        current_atom = atom_index
        pending_bond = None

    while index < len(smiles):
        character = smiles[index]
        if character in "-=#:/\\":
            pending_bond = {"-": 1, "=": 2, "#": 3, ":": 1.5,
                            "/": 1, "\\": 1}[character]
            index += 1
            continue
        if character == "(":
            if current_atom is None:
                raise ValueError("Invalid SMILES: " + smiles)
            branches.append(current_atom)
            index += 1
            continue
        if character == ")":
            if not branches:
                raise ValueError("Invalid SMILES: " + smiles)
            current_atom = branches.pop()
            index += 1
            continue
        if character == ".":
            current_atom = None
            index += 1
            continue
        if character.isdigit() or character == "%":
            if current_atom is None:
                raise ValueError("Invalid SMILES: " + smiles)
            if character == "%":
                ring_label = smiles[index + 1:index + 3]
                if len(ring_label) != 2 or not ring_label.isdigit():
                    raise ValueError("Invalid SMILES ring label: " + smiles)
                index += 3
            else:
                ring_label = character
                index += 1
            if ring_label in rings:
                other_atom, stored_bond = rings.pop(ring_label)
                order = pending_bond or stored_bond
                if order is None:
                    order = (
                        1.5
                        if atoms[current_atom]["aromatic"]
                        and atoms[other_atom]["aromatic"]
                        else 1
                    )
                atoms[current_atom]["bonds"].append((other_atom, order))
                atoms[other_atom]["bonds"].append((current_atom, order))
            else:
                rings[ring_label] = (current_atom, pending_bond)
            pending_bond = None
            continue
        if character == "[":
            closing = smiles.find("]", index + 1)
            if closing < 0:
                raise ValueError("Invalid SMILES: " + smiles)
            token = smiles[index + 1:closing]
            match = re.match(r"\d*([A-Z][a-z]?|[a-z])", token)
            if match is None:
                raise ValueError("Invalid SMILES atom: [" + token + "]")
            raw_symbol = match.group(1)
            aromatic = raw_symbol.islower()
            symbol = raw_symbol.capitalize()
            hydrogen_match = re.search(r"H(\d*)", token[match.end():])
            explicit_hydrogens = (
                int(hydrogen_match.group(1) or "1") if hydrogen_match else 0
            )
            charge_match = re.search(r"([+-])(\d*)", token[match.end():])
            charge = 0
            if charge_match:
                charge = int(charge_match.group(2) or "1")
                if charge_match.group(1) == "-":
                    charge *= -1
            add_atom(symbol, aromatic, charge, explicit_hydrogens)
            index = closing + 1
            continue

        raw_symbol = smiles[index:index + 2]
        if raw_symbol not in ("Cl", "Br"):
            raw_symbol = character
        aromatic = raw_symbol.islower()
        symbol = raw_symbol.capitalize()
        if symbol not in ELEMENTS_BY_SYMBOL:
            raise ValueError("Invalid SMILES atom near: " + smiles[index:])
        add_atom(symbol, aromatic)
        index += len(raw_symbol)

    if branches or rings or pending_bond is not None or not atoms:
        raise ValueError("Invalid SMILES: " + smiles)

    # Convert aromatic bonds to a consistent alternating single/double pattern.
    aromatic_double_bonds = set()
    atoms_with_double_bonds = set()
    for atom_index, parsed_atom in enumerate(atoms):
        for neighbor_index, order in parsed_atom["bonds"]:
            if order != 1.5:
                continue
            pair = tuple(sorted((atom_index, neighbor_index)))
            if (
                atom_index not in atoms_with_double_bonds
                and neighbor_index not in atoms_with_double_bonds
                and not (
                    atoms[atom_index]["symbol"] == "N"
                    and atoms[atom_index]["explicit_hydrogens"]
                )
                and not (
                    atoms[neighbor_index]["symbol"] == "N"
                    and atoms[neighbor_index]["explicit_hydrogens"]
                )
            ):
                aromatic_double_bonds.add(pair)
                atoms_with_double_bonds.update(pair)

    counts = {}
    labels = {}
    for atom_index, parsed_atom in enumerate(atoms):
        symbol = parsed_atom["symbol"]
        if symbol == "H":
            continue
        counts[symbol] = counts.get(symbol, 0) + 1
        labels[atom_index] = symbol + str(counts[symbol])

    molecular_map = {}
    hydrogen_count = 0
    lone_pair_count = 0
    for atom_index, parsed_atom in enumerate(atoms):
        symbol = parsed_atom["symbol"]
        if symbol == "H":
            continue
        element_data = ELEMENTS_BY_SYMBOL[symbol]
        bond_valence = 0
        for neighbor_index, order in parsed_atom["bonds"]:
            if order == 1.5:
                pair = tuple(sorted((atom_index, neighbor_index)))
                if symbol == "N":
                    bond_valence += 1
                else:
                    bond_valence += 2 if pair in aromatic_double_bonds else 1
            else:
                bond_valence += order
        bond_valence += parsed_atom["explicit_hydrogens"]
        if parsed_atom["aromatic"] and symbol == "N" and not parsed_atom["explicit_hydrogens"]:
            allowed_valences = [
                3 if any(order != 1.5 for _, order in parsed_atom["bonds"]) else 2
            ]
        else:
            allowed_valences = sorted(
                valence + parsed_atom["charge"]
                for valence in element_data["allowed_valences"]
            )
        target_valence = next(
            (value for value in allowed_valences if value >= bond_valence),
            None,
        )
        if target_valence is None:
            raise ValueError("Unsupported valence for " + symbol + " in " + smiles)
        implicit_hydrogens = max(0, int(round(target_valence - bond_valence)))
        attached_atoms = []
        total_valence = bond_valence + implicit_hydrogens
        for neighbor_index, order in parsed_atom["bonds"]:
            neighbor_symbol = atoms[neighbor_index]["symbol"]
            if neighbor_symbol == "H":
                hydrogen_count += 1
                neighbor_label = "H" + str(hydrogen_count)
            else:
                neighbor_label = labels[neighbor_index]
            pair = tuple(sorted((atom_index, neighbor_index)))
            bond_order = 2 if pair in aromatic_double_bonds else order
            attached_atoms.extend([neighbor_label] * max(1, int(bond_order)))
        for _ in range(parsed_atom["explicit_hydrogens"] + implicit_hydrogens):
            hydrogen_count += 1
            attached_atoms.append("H" + str(hydrogen_count))

        lone_pairs = max(
            0,
            (element_data["valence_electrons"] - parsed_atom["charge"]
             - int(round(total_valence))) // 2,
        )
        for _ in range(lone_pairs):
            lone_pair_count += 1
            attached_atoms.append("lp" + str(lone_pair_count))
        molecular_map[labels[atom_index]] = attached_atoms

    return molecular_map


def carbon_map_from_compound(compound):
    """Make a molecule structure map from a PubChem compound."""
    # Use the compound's SMILES text to build the atom map.
    smiles = compound.isomeric_smiles
    if smiles is None:
        raise ValueError("Compound does not contain a SMILES representation.")
    return carbon_map_from_smiles(smiles)


def carbon_map(identifier, namespace="name"):
    """Look up a molecule on PubChem and return its structure map."""
    # A number is treated as a PubChem ID; other text is searched as a name.
    if isinstance(identifier, int):
        compound = pcp.Compound.from_cid(identifier)
    else:
        compounds = pcp.get_compounds(identifier, namespace)
        if not compounds:
            raise ValueError("No compound found for " + repr(identifier))
        compound = compounds[0]
    # Convert the first result into the structure dictionary.
    return carbon_map_from_compound(compound)


def main(filename=None):
    """Ask for a molecule, use its saved structure, or look it up if it is new."""
    path = _resolve_data_path(filename)
    if len(sys.argv) > 1:
        identifier = sys.argv[1]
    else:
        identifier = input("Enter a molecule name or PubChem CID: ").strip()

    if not identifier:
        print("Enter a molecule name or PubChem CID.")
        return

    cache_key = str(identifier).strip().lower()
    molecules = load_molecule_map(path)
    if cache_key in molecules:
        print("Loaded {} from the saved molecule file.".format(identifier))
        return molecules[cache_key]

    if identifier.isdigit():
        identifier = int(identifier)

    try:
        molecular_map = carbon_map(identifier)
        print(molecular_map)
        molecules[cache_key] = molecular_map
        save_molecule_map(molecules, path)
        print("Molecule structure saved to {}.".format(path))
        return molecular_map
    except ValueError as error:
        print("Error:", error)


# Run the input flow only when this file is started directly.
if __name__ == "__main__":
    main()
