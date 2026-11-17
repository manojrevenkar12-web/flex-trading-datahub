import numpy as np

from ftd.ingest import land


def test_dbt_builds_and_every_test_passes(quick):
    assert quick["build"]["ok"], quick["build"]["failed"]


def test_landing_twice_lands_nothing_and_resent_files_are_skipped(quick):
    again = land(quick["work"] / "lake")
    assert again["landed"] == 0 and again["duplicate_deliveries"] == 0
    m = quick["sql"]("select status, count(*) as n from stg_deliveries group by 1")
    assert dict(zip(m["status"], m["n"])).get("duplicate", 0) == quick["planted"]["resent_files"]


def test_the_night_summer_time_ends_has_100_quarter_hours_for_both_metering_operators(quick):
    q = quick["sql"]("""select mdm, count(distinct qh_start_utc) as n from int_meter_readings
                        where cast(timezone('Europe/Berlin', timezone('UTC', qh_start_utc)) as date) = date '2026-10-25'
                        and obis = '1-0:1.8.0' group by mdm""")
    assert set(q["n"]) == {100}
    naive = quick["sql"]("""select count(distinct qh_start_utc) as n from meters where obis = '1-0:1.8.0'
                            and cast(timezone('Europe/Berlin', timezone('UTC', qh_start_utc)) as date) = date '2026-10-25'""", "naive")
    assert naive["n"][0] == 100            # the times exist, but the operator without offsets lands two hours on one
    doubled = quick["sql"]("""select count(*) as n from (select meter_id, qh_start_utc, count(*) c from meters
                              where obis = '1-0:1.8.0' and version = 1 group by 1, 2 having count(*) > 1)""", "naive")
    assert doubled["n"][0] > 0


def test_wh_and_kwh_meet_in_kwh(quick):
    r = quick["sql"]("select mdm, avg(kwh) as kwh from int_meter_readings where obis = '1-0:1.8.0' group by mdm")
    assert r["kwh"].between(0.01, 1.0).all()


def test_a_measured_value_replaces_the_substitute_sent_first(quick):
    assert quick["sql"]("select count(*) as n from int_meter_readings where status = 'substitute'")["n"][0] == 0


def test_positions_come_from_the_latest_version_of_each_trade(quick):
    p = quick["sql"]("select qh_start_utc, da_mw, id_mw from fct_portfolio_qh").merge(quick["truth"], on="qh_start_utc", suffixes=("", "_t"))
    assert np.allclose(p["da_mw"], p["da_mw_t"], atol=1e-9) and np.allclose(p["id_mw"], p["id_mw_t"], atol=1e-9)


def test_settles_on_the_final_imbalance_price(quick):
    p = quick["sql"]("select qh_start_utc, rebap_eur_mwh, rebap_is_final from fct_portfolio_qh").merge(quick["truth"], on="qh_start_utc", suffixes=("", "_t"))
    assert p["rebap_is_final"].all() and np.allclose(p["rebap_eur_mwh"], p["rebap_eur_mwh_t"])


def test_stuck_registers_are_found_and_estimated(quick):
    found = set(quick["sql"]("select meter_id from dq_stuck_meters")["meter_id"])
    assert found == set(quick["planted"]["stuck_meters"])
    assert quick["sql"]("select sum(estimated_values) as n from fct_portfolio_qh")["n"][0] > 0


def test_imbalance_cost_is_fully_explained(quick):
    f = quick["sql"]("select * from fct_portfolio_qh")
    parts = f[[c for c in f if c.startswith("attr_")]].sum(axis=1)
    assert np.allclose(parts, f["imbalance_cost_eur"], atol=1e-6)


def test_features_only_use_forecasts_issued_by_the_gate(quick):
    f = quick["sql"]("select weather_issued_at_utc, gate_utc from feat_load_qh where weather_issued_at_utc is not null")
    assert (f["weather_issued_at_utc"] <= f["gate_utc"]).all()
    naive = quick["sql"]("""select count(*) as n from read_parquet('""" + str(quick["work"] / "lake/bronze/weather/*.parquet") + """')""", "naive")
    assert naive["n"][0] > 0


def test_device_counters_never_give_negative_energy(quick):
    assert quick["sql"]("select min(kwh) as m from int_device_qh")["m"][0] >= -1e-9
