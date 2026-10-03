from job_radar_common.seniority import is_senior


def test_rejects_senior_english():
    assert is_senior("Senior Backend Engineer")


def test_rejects_senior_portuguese():
    assert is_senior("Analista Desenvolvedor Sênior")


def test_rejects_sr_abbreviation():
    assert is_senior("Desenvolvedor Backend Sr")
    assert is_senior("Desenvolvedor Backend Sr.")


def test_accepts_pleno_and_junior():
    assert not is_senior("Desenvolvedor Python Pleno")
    assert not is_senior("Junior Python Developer")


def test_does_not_false_positive_on_unrelated_substrings():
    assert not is_senior("Desenvolvedor Fullstack")
