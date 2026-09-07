"""Fail closed on registration count and persisted gallery quality."""
from pathlib import Path

import numpy as np


class RegistrationError(RuntimeError):
    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f'{code}: {message}')

    def as_dict(self):
        return {'code': self.code, 'message': self.message, **self.details}


def validate_registration_config(mode, expected_persons):
    if mode not in {'sequential', 'lineup'} or type(expected_persons) is not int or not 1 <= expected_persons <= 6:
        raise RegistrationError('registration_config_required', 'Specify sequential or lineup enrollment and an expected person count from 1 to 6.')


def validate_detected_count(detected: int, expected_persons: int | None):
    if not 1 <= detected <= 6 or (expected_persons is not None and detected != expected_persons):
        raise RegistrationError('registration_count_mismatch',
                                'Registration headcount does not match the requested count.',
                                expected_persons=expected_persons, detected_persons=detected)


def validate_gallery_samples(root: Path, student_ids: list[str], expected_persons: int | None) -> list[str]:
    validate_detected_count(len(student_ids), expected_persons)
    if len(set(student_ids)) != len(student_ids) or any(Path(s).name != s or s in {'.', '..'} for s in student_ids):
        raise RegistrationError('registration_quality_failed', 'Registration identities are invalid.')
    dimensions = {'face': set(), 'body': set()}
    for student in student_ids:
        directory = root / student
        for kind in dimensions:
            valid = []
            for path in directory.glob(f'{kind}_*.npy'):
                try:
                    vector = np.load(path, allow_pickle=False)
                    if (vector.ndim == 1 and vector.size > 0 and np.issubdtype(vector.dtype, np.number)
                            and np.isfinite(vector).all() and float(np.linalg.norm(vector)) > 1e-8):
                        valid.append(vector)
                except (OSError, ValueError, TypeError, EOFError):
                    continue
            if not valid:
                raise RegistrationError('registration_quality_failed', 'Each person needs valid frontal face and body samples.', student_id=student)
            dimensions[kind].update(v.size for v in valid)
    if any(len(sizes) != 1 for sizes in dimensions.values()):
        raise RegistrationError('registration_quality_failed', 'Registration sample dimensions are inconsistent.')
    actual = {p.name for p in root.iterdir() if p.is_dir()} if root.is_dir() else set()
    if actual != set(student_ids):
        raise RegistrationError('registration_count_mismatch', 'Persisted gallery identities do not match registration.')
    return student_ids
