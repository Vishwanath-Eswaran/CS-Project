try:
    from .moleculeobj import molecule
except ImportError:  # pragma: no cover - direct script execution fallback
    from moleculeobj import molecule

from vpython import color, cross, dot, mag, norm, rate, scene, vector

DAMPING = 0.98
MAX_PAIR_FORCE = 50
MAX_ATOM_SPEED = 20


def keep_bond_lengths(bonds):
    """Keep each bond at the sum of its atoms' radii."""
    for _ in range(12):
        largest_error = 0
        for first, second in bonds:
            direction = second.ball.pos - first.ball.pos
            distance = mag(direction)
            if distance == 0:
                direction = vector(1, 0, 0)
                distance = 1
            error = distance - (first.rad + second.rad)
            largest_error = max(largest_error, abs(error))
            correction = direction * (error / (2 * distance))
            first.ball.pos += correction
            second.ball.pos -= correction
        if largest_error < 0.001:
            break


def bond_side(first, second):
    """Return a direction perpendicular to the bond for parallel bond lines."""
    direction = norm(second.ball.pos - first.ball.pos)
    reference = vector(0, 0, 1)
    if abs(dot(direction, reference)) > 0.9:
        reference = vector(0, 1, 0)
    return norm(cross(direction, reference))


def render(mole, width=None, height=None, background=None):
    """Show the molecule and keep moving atoms in the 3D scene."""
    # Set the scene color and build the molecule's atom objects and spheres.
    if width is not None:
        scene.width = width
    if height is not None:
        scene.height = height
    scene.background = background if background is not None else color.gray(0.5)
    prop = molecule(mole)  
    atmobj = prop.atmobj 
    bond_cylinders = prop.cylinders()
    bonds = []
    seen_bonds = set()
    for center, neighbors in mole.items():
        for neighbor in neighbors:
            if atmobj[center].symbol == "lp" or atmobj[neighbor].symbol == "lp":
                continue
            pair = tuple(sorted((center, neighbor)))
            if pair not in seen_bonds:
                seen_bonds.add(pair)
                bonds.append((atmobj[center], atmobj[neighbor]))
    geometry_bonds = []
    seen_geometry_bonds = set()
    for atom in atmobj.values():
        for neighbor in atom.attached:
            pair = tuple(sorted((atom.name, neighbor.name)))
            if pair not in seen_geometry_bonds:
                seen_geometry_bonds.add(pair)
                geometry_bonds.append((atom, neighbor))
    atom_labels = list(atmobj)
    bonded_pairs = {
        frozenset((first.name, second.name))
        for first, second in geometry_bonds
    }
    dt = 0.02
    # Repeat these steps so the molecule keeps moving on the screen.
    while True:
        try:
            # Clear old forces before calculating the forces for this frame.
            for atom in atmobj.values():
                atom.force=vector(0,0,0)
            # Make atoms that are not bonded push away from each other.
            for index, first_label in enumerate(atom_labels):
                for next_index in range(index + 1, len(atom_labels)):
                    second_label = atom_labels[next_index]
                    if frozenset((first_label, second_label)) in bonded_pairs:
                        continue
                    a1 = atmobj[first_label]
                    a2 = atmobj[second_label]
                    r12 = a1.ball.pos - a2.ball.pos
                    distance = mag(r12)
                    if distance == 0:
                        continue
                    q = 10
                    factor = 1e-6
                    force_magnitude = min(
                        (9 * 10**9) * (q**2) * factor / max(distance**2, 1),
                        MAX_PAIR_FORCE,
                    )
                    force = norm(r12) * force_magnitude
                    a1.force += force
                    a2.force -= force

            # Move each atom once, averaging the force across its unique bonds.
            for atom in atmobj.values():
                neighbors = list({
                    neighbor.name: neighbor for neighbor in atom.attached
                }.values())
                if not neighbors:
                    continue
                transverse_force = vector(0, 0, 0)
                for neighbor in neighbors:
                    direction = atom.ball.pos - neighbor.ball.pos
                    distance = mag(direction)
                    if distance == 0:
                        continue
                    transverse_force += (
                        atom.force
                        - (dot(atom.force, direction) / distance**2) * direction
                    )
                acceleration = transverse_force / len(neighbors) / float(atom.mass)
                atom.velocity = (atom.velocity + acceleration * dt) * DAMPING
                speed = mag(atom.velocity)
                if speed > MAX_ATOM_SPEED:
                    atom.velocity = norm(atom.velocity) * MAX_ATOM_SPEED
                atom.ball.pos += atom.velocity * dt
            keep_bond_lengths(geometry_bonds)
            for bond, first, second, offset in bond_cylinders:
                side = bond_side(first, second)
                bond.pos = first.ball.pos + side * offset
                bond.axis = second.ball.pos - first.ball.pos
            # Keep the display updating at a steady speed.
            rate(1000000000000)
        except Exception:
            break
