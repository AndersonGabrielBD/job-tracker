from job_radar_common.location import is_in_scope


def test_remote_job_anywhere_is_in_scope():
    assert is_in_scope({"is_remote": True, "country": "US", "city": ""})


def test_brazil_remote_is_in_scope():
    assert is_in_scope({"is_remote": True, "country": "BR", "city": ""})


def test_brazil_onsite_maceio_is_in_scope():
    assert is_in_scope({"is_remote": False, "country": "BR", "city": "Maceió"})


def test_brazil_onsite_maceio_via_location_raw():
    assert is_in_scope({
        "is_remote": False, "country": "BR", "city": "",
        "location_raw": "Maceio - AL",
    })


def test_brazil_onsite_other_city_is_out_of_scope():
    assert not is_in_scope({"is_remote": False, "country": "BR", "city": "São Paulo"})


def test_non_brazil_onsite_is_out_of_scope():
    assert not is_in_scope({"is_remote": False, "country": "US", "city": "New York"})
