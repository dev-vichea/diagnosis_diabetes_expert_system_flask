-- Example SQL seed snippets for diagnostic lab findings and rules.
-- Adjust enum/casting syntax for your SQL dialect.

-- 1) Findings (tbl_symptoms)
INSERT INTO tbl_symptoms
    (code, name, question_text, input_type, unit, category, allow_unknown, active, priority_order, created_at, updated_at)
VALUES
    ('FBS', 'Fasting Blood Sugar', 'FBS / fasting blood glucose (mg/dL)', 'NUMBER', 'mg/dL', 'HAB_LAB', 1, 1, 11, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('HBA1C', 'HbA1c', 'HbA1c (%)', 'NUMBER', '%', 'HAB_LAB', 1, 1, 21, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('RANDOM_GLUCOSE', 'Random glucose', 'Random glucose (mg/dL)', 'NUMBER', 'mg/dL', 'HAB_LAB', 1, 1, 31, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('OGTT75_FAST', 'OGTT 75 g fasting', '75 g OGTT fasting glucose (mg/dL)', 'NUMBER', 'mg/dL', 'HAB_LAB', 1, 1, 32, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('OGTT75_1H', 'OGTT 75 g 1-hour', '75 g OGTT 1-hour glucose (mg/dL)', 'NUMBER', 'mg/dL', 'HAB_LAB', 1, 1, 33, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('OGTT75_2H', 'OGTT 75 g 2-hour', '75 g OGTT 2-hour glucose (mg/dL)', 'NUMBER', 'mg/dL', 'HAB_LAB', 1, 1, 34, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 2) Rule set
INSERT INTO tbl_rule_sets (version, active, released_at, notes)
VALUES (2, 1, CURRENT_TIMESTAMP, 'Diagnostic lab thresholds');

-- 3) Rules (tbl_rules) - sample columns
-- NOTE: replace disease_id with your real disease keys.
INSERT INTO tbl_rules
    (rule_code, title, rule_type, version, rule_set_id, disease_id, base_confidence, max_conf_without_labs, confidence_bonus_max,
     min_required_matches, stop_engine_on_match, risk_level, priority, active, created_at, updated_at)
VALUES
    ('R_DGN_001', 'Diabetes by FBS', 'diagnostic', 1, (SELECT id FROM tbl_rule_sets WHERE version=2), (SELECT id FROM tbl_diseases WHERE code='TYPE2_DM'),
     0.920, 0.700, NULL, 1, 0, 'HIGH', 140, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('R_DGN_002', 'Diabetes by HbA1c', 'diagnostic', 1, (SELECT id FROM tbl_rule_sets WHERE version=2), (SELECT id FROM tbl_diseases WHERE code='TYPE2_DM'),
     0.920, 0.700, NULL, 1, 0, 'HIGH', 139, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('R_DGN_003', 'Prediabetes by FBS', 'diagnostic', 1, (SELECT id FROM tbl_rule_sets WHERE version=2), (SELECT id FROM tbl_diseases WHERE code='PREDIABETES'),
     0.880, 0.750, NULL, 1, 0, 'MEDIUM', 132, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('R_DGN_004', 'Prediabetes by HbA1c', 'diagnostic', 1, (SELECT id FROM tbl_rule_sets WHERE version=2), (SELECT id FROM tbl_diseases WHERE code='PREDIABETES'),
     0.880, 0.750, NULL, 1, 0, 'MEDIUM', 131, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('R_DGN_005', 'GDM one-step 75g OGTT', 'diagnostic', 1, (SELECT id FROM tbl_rule_sets WHERE version=2), (SELECT id FROM tbl_diseases WHERE code='GDM'),
     0.940, 0.700, NULL, 1, 0, 'HIGH', 145, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 4) Rule conditions (tbl_rule_conditions)
-- Diabetes by FBS: FBS >= 126
INSERT INTO tbl_rule_conditions (rule_id, symptom_id, finding_code, operator, value, values_json, score_points, weight, is_required, negate, created_at)
VALUES
(
  (SELECT id FROM tbl_rules WHERE rule_code='R_DGN_001'),
  (SELECT id FROM tbl_symptoms WHERE code='FBS'),
  'FBS', 'GTE', '126', '[126]', 0, 1.000, 1, 0, CURRENT_TIMESTAMP
);

-- Diabetes by HbA1c: HBA1C >= 6.5
INSERT INTO tbl_rule_conditions (rule_id, symptom_id, finding_code, operator, value, values_json, score_points, weight, is_required, negate, created_at)
VALUES
(
  (SELECT id FROM tbl_rules WHERE rule_code='R_DGN_002'),
  (SELECT id FROM tbl_symptoms WHERE code='HBA1C'),
  'HBA1C', 'GTE', '6.5', '[6.5]', 0, 1.000, 1, 0, CURRENT_TIMESTAMP
);

-- Prediabetes by FBS: BETWEEN [100,125]
INSERT INTO tbl_rule_conditions (rule_id, symptom_id, finding_code, operator, value, values_json, score_points, weight, is_required, negate, created_at)
VALUES
(
  (SELECT id FROM tbl_rules WHERE rule_code='R_DGN_003'),
  (SELECT id FROM tbl_symptoms WHERE code='FBS'),
  'FBS', 'BETWEEN', '100', '[100,125]', 0, 1.000, 1, 0, CURRENT_TIMESTAMP
);

-- Prediabetes by HbA1c: BETWEEN [5.7,6.4]
INSERT INTO tbl_rule_conditions (rule_id, symptom_id, finding_code, operator, value, values_json, score_points, weight, is_required, negate, created_at)
VALUES
(
  (SELECT id FROM tbl_rules WHERE rule_code='R_DGN_004'),
  (SELECT id FROM tbl_symptoms WHERE code='HBA1C'),
  'HBA1C', 'BETWEEN', '5.7', '[5.7,6.4]', 0, 1.000, 1, 0, CURRENT_TIMESTAMP
);

-- GDM one-step 75 g OGTT: PREGNANT=true and any one abnormal OGTT value
INSERT INTO tbl_rule_conditions (rule_id, symptom_id, finding_code, operator, value, values_json, score_points, weight, is_required, negate, created_at)
VALUES
(
  (SELECT id FROM tbl_rules WHERE rule_code='R_DGN_005'),
  (SELECT id FROM tbl_symptoms WHERE code='PREGNANT'),
  'PREGNANT', 'EQ', '1', '[1]', 0, 1.000, 1, 0, CURRENT_TIMESTAMP
),
(
  (SELECT id FROM tbl_rules WHERE rule_code='R_DGN_005'),
  (SELECT id FROM tbl_symptoms WHERE code='OGTT75_FAST'),
  'OGTT75_FAST', 'GTE', '92', '[92]', 0, 1.000, 0, 0, CURRENT_TIMESTAMP
),
(
  (SELECT id FROM tbl_rules WHERE rule_code='R_DGN_005'),
  (SELECT id FROM tbl_symptoms WHERE code='OGTT75_1H'),
  'OGTT75_1H', 'GTE', '180', '[180]', 0, 1.000, 0, 0, CURRENT_TIMESTAMP
),
(
  (SELECT id FROM tbl_rules WHERE rule_code='R_DGN_005'),
  (SELECT id FROM tbl_symptoms WHERE code='OGTT75_2H'),
  'OGTT75_2H', 'GTE', '153', '[153]', 0, 1.000, 0, 0, CURRENT_TIMESTAMP
);
