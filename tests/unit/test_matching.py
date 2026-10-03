from job_radar_common.matching import score_job

CORE = [["python", 3], ["aws", 2]]


def test_title_match_scores_higher_than_no_match():
    job = {"title": "Senior Python AWS Engineer", "description": ""}
    score, matched = score_job(job, CORE + [["docker", 1]])
    assert score > 0
    assert "python" in matched
    assert "aws" in matched
    assert "docker" not in matched


def test_no_overlap_scores_zero():
    job = {"title": "Marketing Manager", "description": "social media and branding"}
    score, matched = score_job(job, CORE)
    assert score == 0
    assert matched == []


def test_title_match_weighted_higher_than_description_only_match():
    job_title_match = {"title": "Python Developer", "description": ""}
    job_desc_match = {"title": "Developer", "description": "must know python"}
    score_title, _ = score_job(job_title_match, CORE)
    score_desc, _ = score_job(job_desc_match, CORE)
    assert score_title > score_desc


def test_core_keyword_scores_higher_than_nice_keyword():
    core_job = {"title": "Python Developer", "description": ""}
    nice_job = {"title": "React Developer", "description": ""}
    keywords = [["python", 3], ["react", 1]]
    score_core, _ = score_job(core_job, keywords)
    score_nice, _ = score_job(nice_job, keywords)
    assert score_core > score_nice


def test_score_is_capped_at_100():
    keywords = [["python", 3], ["aws", 3], ["fastapi", 3], ["lambda", 3]]
    job = {"title": "Python AWS FastAPI Lambda Engineer", "description": ""}
    score, _ = score_job(job, keywords)
    assert score == 100
