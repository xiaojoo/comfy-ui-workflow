"""Limb proportions, from SDPose wholebody keypoints.

What the ruler claims to answer is "do the arms and legs read as this body's" -- so it
measures bone lengths as a fraction of the torso, and compares left with right. It does
not claim to count fingers: nothing on this box can, and the model that was asked to try
answered "10 fingers" about a hand that visibly has twelve.

Keypoint order is the OpenPose wholebody layout (18 body points, then face, hands, feet).
"""

BODY = {  # index in pose_keypoints_2d, triples of x, y, score
    "nose": 0, "neck": 1, "r_shoulder": 2, "r_elbow": 3, "r_wrist": 4,
    "l_shoulder": 5, "l_elbow": 6, "l_wrist": 7, "r_hip": 8, "r_knee": 9,
    "r_ankle": 10, "l_hip": 11, "l_knee": 12, "l_ankle": 13,
}

# Bands from the anthropometric medians, widened to take pose and perspective: a standing
# figure seen from the front is not a caliper measurement, and a knee bend shortens the
# projected shin. Deliberately not tighter -- a ruler that fails good images gets ignored.
BANDS = {
    "upper_arm_over_torso": (0.22, 0.40),
    "forearm_over_torso": (0.20, 0.38),
    "thigh_over_torso": (0.35, 0.62),
    "shin_over_torso": (0.28, 0.55),
}


def _pt(person, name):
    k = person["pose_keypoints_2d"]
    i = BODY[name] * 3
    x, y, score = k[i], k[i + 1], k[i + 2]
    return (x, y) if score > 0.25 else None


def _len(a, b):
    if a is None or b is None:
        return None
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _ratio(numer, denom):
    if numer is None or denom in (None, 0):
        return None
    return round(numer / denom, 3)


def ratios(person):
    """The eight bone lengths a proportion check needs, all divided by the torso."""
    neck, r_hip, l_hip = _pt(person, "neck"), _pt(person, "r_hip"), _pt(person, "l_hip")
    hip = ((r_hip[0] + l_hip[0]) / 2, (r_hip[1] + l_hip[1]) / 2) if r_hip and l_hip else None
    r_sh, l_sh = _pt(person, "r_shoulder"), _pt(person, "l_shoulder")
    shoulder = ((r_sh[0] + l_sh[0]) / 2, (r_sh[1] + l_sh[1]) / 2) if r_sh and l_sh else None
    torso = _len(neck, hip) or _len(shoulder, hip)
    out = {}
    for side, (sh, el, wr, hip_k, knee, ankle) in {
        "r": (r_sh, _pt(person, "r_elbow"), _pt(person, "r_wrist"), r_hip,
              _pt(person, "r_knee"), _pt(person, "r_ankle")),
        "l": (l_sh, _pt(person, "l_elbow"), _pt(person, "l_wrist"), l_hip,
              _pt(person, "l_knee"), _pt(person, "l_ankle")),
    }.items():
        out[f"{side}_upper_arm_over_torso"] = _ratio(_len(sh, el), torso)
        out[f"{side}_forearm_over_torso"] = _ratio(_len(el, wr), torso)
        out[f"{side}_thigh_over_torso"] = _ratio(_len(hip_k, knee), torso)
        out[f"{side}_shin_over_torso"] = _ratio(_len(knee, ankle), torso)
    return out


def judge(rs):
    """Which named bands this figure falls outside. Empty list means nothing is claimed.

    A missing keypoint is not a pass: it is reported as unseen, because half a body is
    exactly what a cropped or turned figure gives you, and calling that healthy would
    make the whole table a lie of omission.
    """
    fails, unseen = [], []
    for key, value in rs.items():
        # Only the leading side marker is a prefix: "r_forearm_over_torso" also contains
        # "r_" inside "forearm_over", and stripping that looked up a name that does not
        # exist -- which read as "nothing to check" and turned the whole gate green.
        band = BANDS.get(key[2:] if key[:2] in ("r_", "l_") else key)
        if band is None:
            continue
        if value is None:
            unseen.append(key)
        elif not band[0] <= value <= band[1]:
            fails.append({"key": key, "value": value, "want": list(band)})
    return {"fails": fails, "unseen": unseen, "ok": not fails and not unseen}
