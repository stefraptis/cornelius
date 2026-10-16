-- Procedure registry and the deployed LC model version (Build Guideline,
-- Sections 2, 5 and 14). Idempotent: safe to run on every deploy.

insert into public.procedures (code, name, modality, analysis_enabled, display_order) values
  ('lc',             'Laparoscopic cholecystectomy', 'laparoscopic', true,  10),
  ('robotic_chole',  'Robotic cholecystectomy',      'robotic',      false, 20),
  ('lap_appendectomy', 'Laparoscopic appendectomy',  'laparoscopic', false, 30),
  ('lap_hernia',     'Laparoscopic hernia repair',   'laparoscopic', false, 40),
  ('other',          'Other procedure',              'laparoscopic', false, 999)
on conflict (code) do update set
  name = excluded.name,
  modality = excluded.modality,
  display_order = excluded.display_order;

-- Model class names (code) are what the pipeline emits; name is the display
-- name shown in the app; color is the fixed data color used everywhere.
-- Codes follow the Cholec80 label files. They are confirmed against the
-- inference code in M2; if the pipeline emits different strings (for example
-- "Specimen Bag" with a space), only this seed changes.
insert into public.model_versions (procedure_code, name, architecture, phase_labels, tool_labels, metrics, thresholds, is_active)
values (
  'lc',
  'lc-effnetv2s-bilstm-v1',
  'Stage 1: EfficientNet-V2-S, two heads (multi-label instrument presence, frame-level phase). Stage 2: Bi-LSTM over the frame sequence for temporally consistent phases. Frames sampled at 1 fps.',
  '[
    {"code": "Preparation",                 "name": "Preparation",                 "color": "#8C8C84", "order": 1},
    {"code": "CalotTriangleDissection",     "name": "Calot''s Triangle Dissection", "color": "#2F6B4F", "order": 2},
    {"code": "ClippingCutting",             "name": "Clipping and Cutting",        "color": "#B5532E", "order": 3},
    {"code": "GallbladderDissection",       "name": "Gallbladder Dissection",      "color": "#C9A227", "order": 4},
    {"code": "GallbladderPackaging",        "name": "Gallbladder Packaging",       "color": "#6D5BA8", "order": 5},
    {"code": "CleaningCoagulation",         "name": "Cleaning and Coagulation",    "color": "#3E8E8A", "order": 6},
    {"code": "GallbladderRetraction",       "name": "Gallbladder Retraction",      "color": "#A64D79", "order": 7}
  ]'::jsonb,
  '[
    {"code": "Grasper",      "name": "Grasper",            "color": "#3D3D3A", "order": 1},
    {"code": "Bipolar",      "name": "Bipolar Forceps",    "color": "#C27C2C", "order": 2},
    {"code": "Hook",         "name": "Hook",               "color": "#6E8B3D", "order": 3},
    {"code": "Scissors",     "name": "Scissors",           "color": "#A23B3B", "order": 4},
    {"code": "Clipper",      "name": "Clip Applier",       "color": "#7A5C99", "order": 5},
    {"code": "Irrigator",    "name": "Suction-Irrigation", "color": "#2E7D7A", "order": 6},
    {"code": "SpecimenBag",  "name": "Retrieval Bag",      "color": "#B0857A", "order": 7}
  ]'::jsonb,
  '{
    "dataset": "Cholec80",
    "validation": "video-level 5-fold cross-validation",
    "phase_balanced_accuracy": {"mean": 95.73, "std": 0.59, "unit": "%"},
    "tool_map": {"mean": 95.47, "std": 0.82, "unit": "%"}
  }'::jsonb,
  '{"low_confidence_warning": 0.60, "quiz_min_confidence": 0.90}'::jsonb,
  true
)
on conflict (procedure_code, name) do update set
  architecture = excluded.architecture,
  phase_labels = excluded.phase_labels,
  tool_labels = excluded.tool_labels,
  metrics = excluded.metrics,
  thresholds = excluded.thresholds,
  is_active = excluded.is_active;

update public.procedures p
set model_version_id = mv.id
from public.model_versions mv
where p.code = 'lc' and mv.procedure_code = 'lc' and mv.name = 'lc-effnetv2s-bilstm-v1';
