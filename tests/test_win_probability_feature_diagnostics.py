import numpy as np

from cs2eye.analytics.win_probability import WinProbabilityModel
from cs2eye.analytics.win_probability_config import WIN_PROBABILITY_FEATURE_REGISTRY,WIN_PROBABILITY_FEATURES
from cs2eye.services.win_probability_feature_diagnostics_service import diagnose_feature_matrix


def rows_for(primary,secondary=None):
    secondary=secondary if secondary is not None else np.zeros(len(primary))
    return [{key:float(primary[i]) if key=="team_strength_difference" else float(secondary[i]) if key=="raw_matchup_centered" else float(((i*(j+3))%17-8)/100) for j,key in enumerate(WIN_PROBABILITY_FEATURES)} for i in range(len(primary))]


def trained(rows,targets):
    return WinProbabilityModel.train(rows,targets).artifact


def feature(report,key):
    return next(item for item in report["features"] if item["feature"]==key)


def test_obvious_positive_feature_is_stable_and_reproducible():
    x=np.linspace(-2,2,120);targets=(x>0).astype(int).tolist();rows=rows_for(x)
    artifact=trained(rows,targets)
    first=diagnose_feature_matrix(rows,targets,artifact,bootstrap_runs=20,seed=42)
    second=diagnose_feature_matrix(rows,targets,artifact,bootstrap_runs=20,seed=42)
    item=feature(first,"team_strength_difference")
    assert item["coefficient"]>0 and item["univariate_coefficient"]>0 and item["target_correlation"]>0
    assert item["bootstrap"]==feature(second,"team_strength_difference")["bootstrap"]
    assert item["diagnostic_status"]=="stable"


def test_consistent_inverse_signal_is_distinguished():
    x=np.linspace(-2,2,120);targets=(x<0).astype(int).tolist();rows=rows_for(x)
    item=feature(diagnose_feature_matrix(rows,targets,trained(rows,targets),bootstrap_runs=20),"team_strength_difference")
    assert item["target_correlation"]<0 and item["univariate_coefficient"]<0
    assert item["diagnostic_status"]=="consistent_inverse_signal"


def test_correlated_features_are_reported_as_redundant():
    x=np.linspace(-2,2,120);x2=x+.001*np.sin(np.arange(120));targets=(x>0).astype(int).tolist();rows=rows_for(x,x2)
    report=diagnose_feature_matrix(rows,targets,trained(rows,targets),bootstrap_runs=10)
    pair=next(item for item in report["redundancy_candidates"] if set(item["features"])=={"team_strength_difference","raw_matchup_centered"})
    assert pair["correlation"]>.99
    assert any(set(group["features"])>={"team_strength_difference","raw_matchup_centered"} for group in report["multicollinearity_groups"])


def test_feature_registry_is_explicit_and_orientation_is_antisymmetric():
    assert set(WIN_PROBABILITY_FEATURE_REGISTRY)==set(WIN_PROBABILITY_FEATURES)
    values={key:(index+1)/100 for index,key in enumerate(WIN_PROBABILITY_FEATURES)}
    reversed_values={key:-value for key,value in values.items()}
    for key in WIN_PROBABILITY_FEATURES:
        assert WIN_PROBABILITY_FEATURE_REGISTRY[key]["expected_direction"]=="positive"
        assert WIN_PROBABILITY_FEATURE_REGISTRY[key]["expected_symmetry"]=="antisymmetric"
        assert values[key]==-reversed_values[key]
