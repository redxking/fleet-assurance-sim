from fleet_sim.experiments.stage1_research import (
    run_nh1_coupled_envelope,
    run_nh2_attack_reachability,
    run_nh4_admission_trajectory,
)


def test_nh1_harness_runs_and_has_heldout_data():
    df, result, metrics = run_nh1_coupled_envelope(seed=11, n_samples=300)
    assert {"train", "test"}.issubset(set(df.split))
    assert 0.0 <= metrics["auc_coupled"] <= 1.0
    assert result.evidence_level == "model-conditioned demonstration"


def test_nh2_operator_experiment_runs():
    df, result, metrics = run_nh2_attack_reachability(seed=11, n=70, replications=3)
    assert len(df) > 0
    assert metrics["test_scenarios"] > 2
    assert result.hypothesis == "NH2"


def test_nh4_same_final_population():
    df, result, metrics = run_nh4_admission_trajectory(seed=11, replications=3)
    final = df.sort_values("time_s").groupby(["profile", "seed"]).tail(1)
    assert final.n_agents.nunique() == 1
    assert metrics["same_final_n"] == 1.0
    assert result.hypothesis == "NH4"
