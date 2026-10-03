from job_radar_common.matching import score_job


def test_title_match_scores_higher_than_no_match():
    job = {"title": "Senior Python AWS Engineer", "description": ""}
    score, matched = score_job(job, ["python", "aws", "lambda", "docker"])
    assert score > 0
    assert "python" in matched
    assert "aws" in matched
    assert "docker" not in matched


def test_no_overlap_scores_zero():
    job = {"title": "Marketing Manager", "description": "social media and branding"}
    score, matched = score_job(job, ["python", "aws"])
    assert score == 0
    assert matched == []


def test_title_match_weighted_higher_than_description_only_match():
    job_title_match = {"title": "Python Developer", "description": ""}
    job_desc_match = {"title": "Developer", "description": "must know python"}
    score_title, _ = score_job(job_title_match, ["python"])
    score_desc, _ = score_job(job_desc_match, ["python"])
    assert score_title > score_desc


def test_score_is_capped_at_100():
    keywords = ["python", "aws", "lambda", "docker", "redis", "fastapi", "postgres", "react"]
    job = {"title": " ".join(keywords) + " extra extra extra", "description": ""}
    score, _ = score_job(job, keywords)
    assert score == 100
