"""Build a starter library of 100 common molecule structures."""

from pathlib import Path

from vsepr.nameProcessing import carbon_map_from_smiles, load_molecule_map, save_molecule_map

PROJECT_DIR = Path(__file__).resolve().parent.parent


# Each entry has a display name and a SMILES string describing its atoms.
MOLECULES = [
    ("Water", "O"),
    ("Methane", "C"),
    ("Ethane", "CC"),
    ("Propane", "CCC"),
    ("Butane", "CCCC"),
    ("Isobutane", "CC(C)C"),
    ("Pentane", "CCCCC"),
    ("Isopentane", "CCC(C)C"),
    ("Neopentane", "CC(C)(C)C"),
    ("Hexane", "CCCCCC"),
    ("Heptane", "CCCCCCC"),
    ("Octane", "CCCCCCCC"),
    ("Nonane", "CCCCCCCCC"),
    ("Decane", "CCCCCCCCCC"),
    ("Ethene", "C=C"),
    ("Propene", "C=CC"),
    ("1-Butene", "C=CCC"),
    ("2-Butene", "C/C=C/C"),
    ("1-Pentene", "C=CCCC"),
    ("1-Hexene", "C=CCCCC"),
    ("Acetylene", "C#C"),
    ("Propyne", "C#CC"),
    ("1-Butyne", "C#CCC"),
    ("2-Butyne", "CC#CC"),
    ("Cyclopropane", "C1CC1"),
    ("Cyclobutane", "C1CCC1"),
    ("Cyclopentane", "C1CCCC1"),
    ("Cyclohexane", "C1CCCCC1"),
    ("Cycloheptane", "C1CCCCCC1"),
    ("Benzene", "c1ccccc1"),
    ("Toluene", "Cc1ccccc1"),
    ("Ethylbenzene", "CCc1ccccc1"),
    ("Styrene", "C=Cc1ccccc1"),
    ("Phenol", "Oc1ccccc1"),
    ("Aniline", "Nc1ccccc1"),
    ("Chlorobenzene", "Clc1ccccc1"),
    ("Fluorobenzene", "Fc1ccccc1"),
    ("Bromobenzene", "Brc1ccccc1"),
    ("Nitrobenzene", "O=[N+]([O-])c1ccccc1"),
    ("Benzoic acid", "O=C(O)c1ccccc1"),
    ("Benzaldehyde", "O=Cc1ccccc1"),
    ("Anisole", "COc1ccccc1"),
    ("Naphthalene", "c1ccc2ccccc2c1"),
    ("Pyridine", "n1ccccc1"),
    ("Pyrrole", "[nH]1cccc1"),
    ("Methanol", "CO"),
    ("Ethanol", "CCO"),
    ("1-Propanol", "CCCO"),
    ("Isopropanol", "CC(O)C"),
    ("1-Butanol", "CCCCO"),
    ("tert-Butanol", "CC(C)(C)O"),
    ("Ethylene glycol", "OCCO"),
    ("Glycerol", "OCC(O)CO"),
    ("Dimethyl ether", "COC"),
    ("Diethyl ether", "CCOCC"),
    ("Tetrahydrofuran", "C1CCOC1"),
    ("Formaldehyde", "C=O"),
    ("Acetaldehyde", "CC=O"),
    ("Propanal", "CCC=O"),
    ("Acetone", "CC(=O)C"),
    ("2-Butanone", "CCC(=O)C"),
    ("Cyclohexanone", "O=C1CCCCC1"),
    ("Formic acid", "O=CO"),
    ("Acetic acid", "CC(=O)O"),
    ("Propionic acid", "CCC(=O)O"),
    ("Butyric acid", "CCCC(=O)O"),
    ("Oxalic acid", "O=C(O)C(=O)O"),
    ("Lactic acid", "CC(O)C(=O)O"),
    ("Citric acid", "O=C(O)CC(O)(C(=O)O)CC(=O)O"),
    ("Methylamine", "CN"),
    ("Ethylamine", "CCN"),
    ("Dimethylamine", "CNC"),
    ("Trimethylamine", "CN(C)C"),
    ("Acetamide", "CC(=O)N"),
    ("Urea", "NC(=O)N"),
    ("Acetonitrile", "CC#N"),
    ("Benzonitrile", "N#Cc1ccccc1"),
    ("Chloroform", "ClC(Cl)Cl"),
    ("Dichloromethane", "ClCCl"),
    ("Carbon tetrachloride", "ClC(Cl)(Cl)Cl"),
    ("Fluoromethane", "CF"),
    ("Chloroethane", "CCCl"),
    ("Bromoethane", "CCBr"),
    ("Iodomethane", "CI"),
    ("Hydrogen sulfide", "S"),
    ("Methanethiol", "CS"),
    ("Dimethyl sulfide", "CSC"),
    ("Sulfur dioxide", "O=S=O"),
    ("Sulfuric acid", "O=S(=O)(O)O"),
    ("Phosphoric acid", "P(=O)(O)(O)O"),
    ("Ammonia", "N"),
    ("Hydrogen peroxide", "OO"),
    ("Carbon dioxide", "O=C=O"),
    ("Glucose", "C([C@@H]1[C@H]([C@@H]([C@H](C(O1)O)O)O)O)O"),
    ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
    ("Caffeine", "Cn1c(=O)c2c(ncn2C)n(C)c1=O"),
    ("Acetaminophen", "CC(=O)Nc1ccc(O)cc1"),
    ("Ibuprofen", "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O"),
    ("Salicylic acid", "O=C(O)c1ccccc1O"),
    ("Glycine", "NCC(=O)O"),
]


def main():
    """Add the molecule structures to molecule.dat and list their names."""
    if len(MOLECULES) != 100:
        raise ValueError("The molecule list must contain exactly 100 entries.")

    # Keep any molecules already saved, including the existing propane entry.
    saved_molecules = load_molecule_map()
    for name, smiles in MOLECULES:
        saved_molecules[name.lower()] = carbon_map_from_smiles(smiles)

    # Save in a format that can also be opened by Python 3.7.
    save_molecule_map(saved_molecules)
    names_path = PROJECT_DIR / "data" / "molecule_names.txt"
    with open(names_path, "w", encoding="utf-8") as names_file:
        names_file.write("\n".join(name for name, _ in MOLECULES) + "\n")

    print("Saved {} molecule structures.".format(len(MOLECULES)))
    print("Wrote the names to {}.".format(names_path))


if __name__ == "__main__":
    main()
