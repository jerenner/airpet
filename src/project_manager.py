# src/project_manager.py
import json
import hashlib
import math
import tempfile
import os
import re
import numpy as np
from copy import deepcopy
from datetime import datetime
from scipy.spatial.transform import Rotation as R
import shutil
import itertools
import random
import time
import threading

from .geometry_types import GeometryState, Solid, Define, Material, Element, Isotope, \
                            LogicalVolume, PhysicalVolumePlacement, Assembly, ReplicaVolume, \
                            DivisionVolume, ParamVolume, OpticalSurface, SkinSurface, \
                            BorderSurface, ParticleSource, GlobalUniformMagneticField, \
                            GlobalUniformElectricField, LocalUniformMagneticField, ScoringState, \
                            LocalUniformElectricField, normalize_detector_feature_generator_entry
from .gdml_parser import GDMLParser
from .gdml_writer import GDMLWriter
from .step_parser import parse_step_file
from .objective_formula import evaluate_objective_formula
from .scoring_artifacts import build_run_manifest_summary, build_scoring_runtime_plan

AUTOSAVE_VERSION_ID = "autosave"


def _normalize_step_import_offset(raw_offset):
    if not isinstance(raw_offset, dict):
        raw_offset = {}

    return {
        'x': str(raw_offset.get('x', '0')),
        'y': str(raw_offset.get('y', '0')),
        'z': str(raw_offset.get('z', '0')),
    }


def _collect_step_import_object_ids(imported_state):
    placements = []
    top_level_placements = []
    seen_placement_ids = set()

    def add_placement(pv):
        if pv and getattr(pv, 'id', None) and pv.id not in seen_placement_ids:
            seen_placement_ids.add(pv.id)
            placements.append(pv)

    for pv in getattr(imported_state, 'placements_to_add', []) or []:
        if pv and getattr(pv, 'id', None) and pv.id not in seen_placement_ids:
            seen_placement_ids.add(pv.id)
            placements.append(pv)
            top_level_placements.append(pv)

    for assembly in imported_state.assemblies.values():
        for pv in getattr(assembly, 'placements', []) or []:
            add_placement(pv)

    for lv in imported_state.logical_volumes.values():
        if getattr(lv, 'content_type', None) == 'physvol' and isinstance(getattr(lv, 'content', None), list):
            for pv in lv.content:
                add_placement(pv)

    return {
        'solid_ids': [solid.id for solid in imported_state.solids.values()],
        'logical_volume_ids': [lv.id for lv in imported_state.logical_volumes.values()],
        'assembly_ids': [assembly.id for assembly in imported_state.assemblies.values()],
        'placement_ids': [pv.id for pv in placements],
        'top_level_placement_ids': [pv.id for pv in top_level_placements],
    }


def _get_step_reimport_target_import_id(options):
    if not isinstance(options, dict):
        return None

    target_import_id = options.get('reimportTargetImportId')
    if isinstance(target_import_id, str):
        target_import_id = target_import_id.strip()
        if target_import_id:
            return target_import_id

    return None


def _build_step_import_provenance_record(temp_path, step_file_stream, options, imported_state, import_id=None):
    import uuid

    source_filename = getattr(step_file_stream, 'filename', None)
    if source_filename:
        source_filename = os.path.basename(source_filename)
    else:
        source_filename = os.path.basename(temp_path)

    sha256 = hashlib.sha256()
    with open(temp_path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            sha256.update(chunk)

    grouping_name = getattr(imported_state, 'grouping_name', None) or options.get('groupingName', 'STEP_Import')
    grouping_name = str(grouping_name)
    object_ids = _collect_step_import_object_ids(imported_state)

    return {
        'import_id': str(import_id).strip() if isinstance(import_id, str) and import_id.strip() else f"step_import_{uuid.uuid4().hex}",
        'source': {
            'format': 'step',
            'filename': source_filename,
            'sha256': sha256.hexdigest(),
            'size_bytes': os.path.getsize(temp_path),
        },
        'options': {
            'grouping_name': grouping_name,
            'placement_mode': str(options.get('placementMode', 'assembly')),
            'parent_lv_name': options.get('parentLVName'),
            'offset': _normalize_step_import_offset(options.get('offset', {})),
            'smart_import_enabled': bool(options.get('smartImport', options.get('smart_import', False))),
        },
        'created_object_ids': object_ids,
        'created_group_names': {
            'solid': f"{grouping_name}_solids" if object_ids['solid_ids'] else None,
            'logical_volume': f"{grouping_name}_lvs" if object_ids['logical_volume_ids'] else None,
            'assembly': f"{grouping_name}_assemblies" if object_ids['assembly_ids'] else None,
        },
    }


def _build_step_import_smart_import_summary(smart_import_report):
    if not isinstance(smart_import_report, dict):
        return None

    if not smart_import_report.get('enabled'):
        return None

    summary = smart_import_report.get('summary')
    if not isinstance(summary, dict):
        return None

    normalized_summary = deepcopy(summary)
    selected_mode_counts = normalized_summary.get('selected_mode_counts', {})
    if not isinstance(selected_mode_counts, dict):
        selected_mode_counts = {}

    primitive_count = int(normalized_summary.get('primitive_count', 0) or 0)
    selected_primitive_count = int(selected_mode_counts.get('primitive', 0) or 0)
    selected_tessellated_count = int(selected_mode_counts.get('tessellated', 0) or 0)

    fallback_reason_counts = {}
    for candidate in smart_import_report.get('candidates', []) or []:
        if not isinstance(candidate, dict):
            continue
        if candidate.get('selected_mode') != 'tessellated':
            continue

        fallback_reason = candidate.get('fallback_reason') or 'no_primitive_match_v1'
        fallback_reason = str(fallback_reason).strip() or 'no_primitive_match_v1'
        fallback_reason_counts[fallback_reason] = fallback_reason_counts.get(fallback_reason, 0) + 1

    top_fallback_reasons = [
        {'reason': reason, 'count': count}
        for reason, count in sorted(fallback_reason_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        'enabled': True,
        'summary': normalized_summary,
        'summary_text': f"{primitive_count} primitive candidates, {selected_tessellated_count} tessellated fallbacks",
        'primitive_candidate_count': primitive_count,
        'selected_primitive_count': selected_primitive_count,
        'selected_tessellated_count': selected_tessellated_count,
        'fallback_reason_counts': fallback_reason_counts,
        'top_fallback_reasons': top_fallback_reasons,
    }


def _normalize_step_import_signature_value(value):
    if isinstance(value, dict):
        return {
            str(key): _normalize_step_import_signature_value(val)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
        }

    if isinstance(value, list):
        return [_normalize_step_import_signature_value(item) for item in value]

    if isinstance(value, tuple):
        return [_normalize_step_import_signature_value(item) for item in value]

    if isinstance(value, np.generic):
        return value.item()

    if hasattr(value, 'to_dict') and callable(value.to_dict):
        try:
            return _normalize_step_import_signature_value(value.to_dict())
        except Exception:
            return str(value)

    return value


def _hash_step_import_signature(payload):
    normalized_payload = _normalize_step_import_signature_value(payload)
    serialized_payload = json.dumps(
        normalized_payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(serialized_payload.encode('utf-8')).hexdigest()


def _find_step_import_pv_in_state(state, pv_id):
    if not state or not isinstance(pv_id, str) or not pv_id.strip():
        return None

    pv_id = pv_id.strip()

    for lv in getattr(state, 'logical_volumes', {}).values():
        if getattr(lv, 'content_type', None) != 'physvol' or not isinstance(getattr(lv, 'content', None), list):
            continue
        for pv in lv.content:
            if getattr(pv, 'id', None) == pv_id:
                return pv

    for assembly in getattr(state, 'assemblies', {}).values():
        for pv in getattr(assembly, 'placements', []) or []:
            if getattr(pv, 'id', None) == pv_id:
                return pv

    return None


def _collect_step_import_leaf_part_records(state, root_placement_ids=None):
    if not state:
        return []

    root_placements = []
    if root_placement_ids is None:
        root_placements = list(getattr(state, 'placements_to_add', []) or [])
    else:
        seen_root_ids = set()
        for pv_id in root_placement_ids:
            pv = _find_step_import_pv_in_state(state, pv_id)
            if pv and getattr(pv, 'id', None) not in seen_root_ids:
                seen_root_ids.add(pv.id)
                root_placements.append(pv)

    root_placements = sorted(
        root_placements,
        key=lambda pv: (
            getattr(pv, 'name', '') or '',
            getattr(pv, 'id', '') or '',
        ),
    )

    records = []

    def _placement_snapshot(pv, include_parent=False):
        snapshot = {
            'volume_kind': 'assembly'
            if getattr(pv, 'volume_ref', None) in getattr(state, 'assemblies', {})
            else 'logical_volume'
            if getattr(pv, 'volume_ref', None) in getattr(state, 'logical_volumes', {})
            else 'missing',
            'copy_number_expr': _normalize_step_import_signature_value(getattr(pv, 'copy_number_expr', None)),
            'position': _normalize_step_import_signature_value(getattr(pv, 'position', None)),
            'rotation': _normalize_step_import_signature_value(getattr(pv, 'rotation', None)),
            'scale': _normalize_step_import_signature_value(getattr(pv, 'scale', None)),
        }
        if include_parent:
            snapshot['parent_lv_name'] = _normalize_step_import_signature_value(getattr(pv, 'parent_lv_name', None))
        return snapshot

    def _solid_snapshot(lv):
        solid = getattr(state, 'solids', {}).get(getattr(lv, 'solid_ref', None))
        if not solid:
            return {
                'solid_ref': getattr(lv, 'solid_ref', None),
                'missing': True,
            }

        return {
            'solid_type': getattr(solid, 'type', None),
            'raw_parameters': _normalize_step_import_signature_value(getattr(solid, 'raw_parameters', None)),
        }

    def _record_leaf_part(lv, path_snapshots):
        part_payload = {
            'path': path_snapshots,
            'leaf': {
                'solid': _solid_snapshot(lv),
            },
        }

        if getattr(lv, 'content_type', None) != 'physvol':
            content = getattr(lv, 'content', None)
            if content is not None:
                part_payload['leaf']['content_type'] = getattr(lv, 'content_type', None)
                if hasattr(content, 'to_dict') and callable(content.to_dict):
                    part_payload['leaf']['content'] = _normalize_step_import_signature_value(content.to_dict())
                else:
                    part_payload['leaf']['content'] = _normalize_step_import_signature_value(content)

        records.append({
            'kind': 'logical_volume',
            'name': getattr(lv, 'name', ''),
            'signature': _hash_step_import_signature(part_payload),
        })

    def _walk_placement(pv, path_snapshots, active_volume_refs):
        if not pv:
            return

        volume_ref = getattr(pv, 'volume_ref', None)
        if isinstance(volume_ref, str) and volume_ref in active_volume_refs:
            return

        next_active_volume_refs = set(active_volume_refs)
        if isinstance(volume_ref, str) and volume_ref:
            next_active_volume_refs.add(volume_ref)

        next_path = path_snapshots + [_placement_snapshot(pv, include_parent=not path_snapshots)]

        lv = getattr(state, 'logical_volumes', {}).get(volume_ref)
        if lv:
            if getattr(lv, 'content_type', None) == 'physvol' and isinstance(getattr(lv, 'content', None), list) and lv.content:
                for child_pv in lv.content:
                    _walk_placement(child_pv, next_path, next_active_volume_refs)
            else:
                _record_leaf_part(lv, next_path)
            return

        assembly = getattr(state, 'assemblies', {}).get(volume_ref)
        if assembly:
            for child_pv in getattr(assembly, 'placements', []) or []:
                _walk_placement(child_pv, next_path, next_active_volume_refs)

    for root_pv in root_placements:
        _walk_placement(root_pv, [], set())

    return records


def _build_step_import_reimport_diff_summary(current_state, target_import_record, imported_state):
    if not current_state or not isinstance(target_import_record, dict) or not imported_state:
        return {
            'summary': {
                'total_before': 0,
                'total_after': 0,
                'unchanged_count': 0,
                'added_count': 0,
                'removed_count': 0,
                'renamed_count': 0,
                'changed_count': 0,
            },
            'added_parts': [],
            'removed_parts': [],
            'renamed_parts': [],
            'changed_parts': [],
        }

    object_ids = target_import_record.get('created_object_ids', {}) or {}
    root_placement_ids = object_ids.get('top_level_placement_ids') or object_ids.get('placement_ids') or []

    before_records = _collect_step_import_leaf_part_records(current_state, root_placement_ids=root_placement_ids)
    after_records = _collect_step_import_leaf_part_records(imported_state)

    before_by_exact_key = {}
    after_by_exact_key = {}
    for index, record in enumerate(before_records):
        before_by_exact_key.setdefault((record['name'], record['signature']), []).append(index)
    for index, record in enumerate(after_records):
        after_by_exact_key.setdefault((record['name'], record['signature']), []).append(index)

    matched_before = set()
    matched_after = set()
    unchanged_count = 0

    for key in sorted(set(before_by_exact_key).intersection(after_by_exact_key)):
        before_indices = before_by_exact_key[key]
        after_indices = after_by_exact_key[key]
        pair_count = min(len(before_indices), len(after_indices))
        for offset in range(pair_count):
            matched_before.add(before_indices[offset])
            matched_after.add(after_indices[offset])
            unchanged_count += 1

    before_by_signature = {}
    after_by_signature = {}
    for index, record in enumerate(before_records):
        if index in matched_before:
            continue
        before_by_signature.setdefault(record['signature'], []).append(index)
    for index, record in enumerate(after_records):
        if index in matched_after:
            continue
        after_by_signature.setdefault(record['signature'], []).append(index)

    renamed_parts = []
    for signature in sorted(set(before_by_signature).intersection(after_by_signature)):
        before_indices = sorted(
            before_by_signature[signature],
            key=lambda index: (before_records[index]['name'], index),
        )
        after_indices = sorted(
            after_by_signature[signature],
            key=lambda index: (after_records[index]['name'], index),
        )
        pair_count = min(len(before_indices), len(after_indices))
        for offset in range(pair_count):
            before_index = before_indices[offset]
            after_index = after_indices[offset]
            matched_before.add(before_index)
            matched_after.add(after_index)
            renamed_parts.append({
                'kind': before_records[before_index]['kind'],
                'before_name': before_records[before_index]['name'],
                'after_name': after_records[after_index]['name'],
                'signature': signature,
            })

    before_by_name = {}
    after_by_name = {}
    for index, record in enumerate(before_records):
        if index in matched_before:
            continue
        before_by_name.setdefault(record['name'], []).append(index)
    for index, record in enumerate(after_records):
        if index in matched_after:
            continue
        after_by_name.setdefault(record['name'], []).append(index)

    changed_parts = []
    for name in sorted(set(before_by_name).intersection(after_by_name)):
        before_indices = sorted(
            before_by_name[name],
            key=lambda index: (before_records[index]['signature'], index),
        )
        after_indices = sorted(
            after_by_name[name],
            key=lambda index: (after_records[index]['signature'], index),
        )
        pair_count = min(len(before_indices), len(after_indices))
        for offset in range(pair_count):
            before_index = before_indices[offset]
            after_index = after_indices[offset]
            matched_before.add(before_index)
            matched_after.add(after_index)
            changed_parts.append({
                'kind': before_records[before_index]['kind'],
                'name': name,
                'before_signature': before_records[before_index]['signature'],
                'after_signature': after_records[after_index]['signature'],
            })

    added_parts = [
        {
            'kind': after_records[index]['kind'],
            'name': after_records[index]['name'],
            'signature': after_records[index]['signature'],
        }
        for index in sorted(
            (index for index in range(len(after_records)) if index not in matched_after),
            key=lambda index: (after_records[index]['name'], after_records[index]['signature'], index),
        )
    ]

    removed_parts = [
        {
            'kind': before_records[index]['kind'],
            'name': before_records[index]['name'],
            'signature': before_records[index]['signature'],
        }
        for index in sorted(
            (index for index in range(len(before_records)) if index not in matched_before),
            key=lambda index: (before_records[index]['name'], before_records[index]['signature'], index),
        )
    ]

    return {
        'summary': {
            'total_before': len(before_records),
            'total_after': len(after_records),
            'unchanged_count': unchanged_count,
            'added_count': len(added_parts),
            'removed_count': len(removed_parts),
            'renamed_count': len(renamed_parts),
            'changed_count': len(changed_parts),
        },
        'added_parts': added_parts,
        'removed_parts': removed_parts,
        'renamed_parts': renamed_parts,
        'changed_parts': changed_parts,
    }


def _build_step_import_reimport_cleanup_policy(reimport_diff_summary):
    if not isinstance(reimport_diff_summary, dict):
        return None

    summary = reimport_diff_summary.get('summary', {})
    removed_count = 0
    if isinstance(summary, dict):
        try:
            removed_count = int(summary.get('removed_count', 0) or 0)
        except Exception:
            removed_count = 0

    return {
        'replacement_mode': 'replace_in_place',
        'obsolete_part_action': 'remove',
        'removed_count': max(removed_count, 0),
        'summary_text': 'Supported STEP reimport replaces the target import in place and removes obsolete imported parts.',
    }


def _normalize_step_import_object_name(value):
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None

class ProjectManager:
    def __init__(self, expression_evaluator):
        self.current_geometry_state = GeometryState()
        self.gdml_parser = GDMLParser()
        
        # Give the project manager an evaluator instance
        self.expression_evaluator = expression_evaluator

        # --- History Management ---
        self.history = []
        self.history_index = -1
        self.MAX_HISTORY_SIZE = 50 # Cap the undo stack
        self.MAX_PARAM_STUDY_RUNS = 2000
        self.MAX_OPTIMIZER_BUDGET = 1000
        self._is_transaction_open = False
        self._pre_transaction_state = None
        self.chat_history = [] # For AI conversation continuity

        # --- Project Management ---
        self.project_name = "untitled"
        self.projects_dir = "projects"
        self.last_state_hash = None # For auto-save change detection
        self.is_changed = False     # Flag for changes
        self.current_version_id = None # Track the currently loaded version

        # --- Track changed objects (for now only tracking certain solids) ---
        self.changed_object_ids = {'solids': set(), 'sources': set() } #, 'lvs': set(), 'defines': set()}

        # --- Active optimization/study run control (M6 safety) ---
        self._run_control_lock = threading.Lock()
        self._active_run_control = None
        self._last_run_control = None

    def _clear_change_tracker(self):
        self.changed_object_ids = {key: set() for key in self.changed_object_ids}

    def start_managed_run(self, kind='optimizer', max_wall_time_seconds=None, metadata=None):
        with self._run_control_lock:
            if self._active_run_control and self._active_run_control.get('status') == 'running':
                return None, "Another run is already active for this project."

            wall = None
            if max_wall_time_seconds is not None:
                try:
                    wall = max(1, int(max_wall_time_seconds))
                except Exception:
                    wall = None

            started_at = time.time()
            run_control = {
                'run_control_id': f"runctl_{datetime.utcnow().strftime('%Y%m%dT%H%M%S_%f')}",
                'kind': str(kind or 'optimizer'),
                'status': 'running',
                'started_at': started_at,
                'max_wall_time_seconds': wall,
                'deadline_at': (started_at + wall) if wall is not None else None,
                'stop_requested': False,
                'stop_reason': None,
                'metadata': dict(metadata or {}),
            }
            self._active_run_control = run_control
            self._last_run_control = dict(run_control)
            return dict(run_control), None

    def request_stop_managed_run(self, reason='user_requested_stop'):
        with self._run_control_lock:
            rc = self._active_run_control
            if not rc or rc.get('status') != 'running':
                return {
                    'active': False,
                    'stop_requested': False,
                    'reason': 'No active run.',
                }

            if not rc.get('stop_requested'):
                rc['stop_requested'] = True
                rc['stop_reason'] = str(reason or 'user_requested_stop')
                rc['stop_requested_at'] = time.time()

            return {
                'active': True,
                'stop_requested': True,
                'run_control': dict(rc),
            }

    def get_managed_run_status(self):
        with self._run_control_lock:
            active = dict(self._active_run_control) if self._active_run_control else None
            last = dict(self._last_run_control) if self._last_run_control else None

        now = time.time()

        def _decorate(rec):
            if not rec:
                return None
            started_at = rec.get('started_at')
            rec['elapsed_seconds'] = (now - started_at) if isinstance(started_at, (int, float)) else None
            deadline_at = rec.get('deadline_at')
            rec['remaining_seconds'] = (deadline_at - now) if isinstance(deadline_at, (int, float)) else None
            return rec

        return {
            'active': _decorate(active),
            'last': _decorate(last),
        }

    def update_managed_run_progress(
        self,
        *,
        total_evaluations=None,
        evaluations_completed=None,
        success_count=None,
        failure_count=None,
        current_run_index=None,
        current_values=None,
        phase=None,
        message=None,
    ):
        with self._run_control_lock:
            rc = self._active_run_control
            if not rc or rc.get('status') != 'running':
                return None

            progress = dict(rc.get('progress') or {})

            if total_evaluations is not None:
                try:
                    progress['total_evaluations'] = max(0, int(total_evaluations))
                except Exception:
                    pass

            if evaluations_completed is not None:
                try:
                    progress['evaluations_completed'] = max(0, int(evaluations_completed))
                except Exception:
                    pass

            if success_count is not None:
                try:
                    progress['success_count'] = max(0, int(success_count))
                except Exception:
                    pass

            if failure_count is not None:
                try:
                    progress['failure_count'] = max(0, int(failure_count))
                except Exception:
                    pass

            if current_run_index is not None:
                try:
                    progress['current_run_index'] = max(0, int(current_run_index))
                except Exception:
                    pass

            if current_values is not None:
                if isinstance(current_values, dict):
                    progress['current_values'] = dict(current_values)
                else:
                    progress['current_values'] = {}

            if phase is not None:
                progress['phase'] = str(phase)

            if message is not None:
                progress['message'] = str(message)

            progress['updated_at'] = time.time()
            rc['progress'] = progress
            self._last_run_control = dict(rc)
            return dict(progress)

    def _should_abort_managed_run(self):
        with self._run_control_lock:
            rc = self._active_run_control
            if not rc or rc.get('status') != 'running':
                return None

            if rc.get('stop_requested'):
                return rc.get('stop_reason') or 'stopped'

            deadline_at = rc.get('deadline_at')
            if isinstance(deadline_at, (int, float)) and time.time() >= deadline_at:
                rc['stop_requested'] = True
                rc['stop_reason'] = 'wall_time_exceeded'
                rc['stop_requested_at'] = time.time()
                return 'wall_time_exceeded'

        return None

    def finish_managed_run(self, status='completed', details=None):
        with self._run_control_lock:
            rc = self._active_run_control
            if not rc:
                return None

            final_status = str(status or 'completed')
            if final_status == 'completed' and rc.get('stop_requested'):
                final_status = 'stopped'

            rc['status'] = final_status
            rc['ended_at'] = time.time()
            if isinstance(details, dict):
                rc['details'] = dict(details)

            self._last_run_control = dict(rc)
            self._active_run_control = None
            return dict(self._last_run_control)

    def _get_project_path(self):
        return os.path.join(self.projects_dir, self.project_name)

    def _get_next_untitled_name(self):
        base = "untitled"
        if not os.path.exists(self._get_project_path(base)):
            return base
        i = 1
        while True:
            name = f"{base}_{i}"
            if not os.path.exists(self._get_project_path(name)):
                return name
            i += 1
        
    def auto_save_project(self):
        if not self.is_changed:
            return False, "No changes to autosave."
        
        project_path = self._get_project_path()
        autosave_version_dir = os.path.join(project_path, "versions", AUTOSAVE_VERSION_ID)
        os.makedirs(autosave_version_dir, exist_ok=True)

        # The file inside is named version.json, just like any other version
        version_filepath = os.path.join(autosave_version_dir, "version.json")
        
        # Save the current state as a JSON string
        json_string = self.save_project_to_json_string()

        with open(version_filepath, 'w') as f:
            f.write(json_string)
        
        self.is_changed = False
        return True, "Autosaved."
    
    def create_empty_project(self):
        self.current_geometry_state = GeometryState()
        
        ## Create a G4_Galactic material
        world_mat = Material(
            name="G4_Galactic", 
            Z_expr="1", 
            A_expr="1.01", 
            density_expr="1.0e-25", 
            state="gas"
        )
        self.current_geometry_state.add_material(world_mat)
        
        # Create a default solid and LV for the world (e.g., a 10m box)
        world_solid_params = {'x': '10000', 'y': '10000', 'z': '10000'}
        world_solid = Solid(name="world_solid", solid_type="box", raw_parameters=world_solid_params)
        self.current_geometry_state.add_solid(world_solid)

        world_lv = LogicalVolume(name="World", solid_ref="world_solid", material_ref="G4_Galactic")
        self.current_geometry_state.add_logical_volume(world_lv)

        # Create a single box to go in the center of the world
        box_solid_params = {'x': '100', 'y': '100', 'z': '100'}
        box_solid = Solid(name="box_solid", solid_type="box", raw_parameters=box_solid_params)
        self.current_geometry_state.add_solid(box_solid)
        box_lv = LogicalVolume(name="box_LV", solid_ref="box_solid", material_ref="G4_Galactic")
        self.current_geometry_state.add_logical_volume(box_lv)
        self.add_physical_volume("World", "box_PV", "box_LV", 
                                 {'x': '0', 'y': '0', 'z': '0'},
                                 {'x': '0', 'y': '0', 'z': '0'}, 
                                 {'x': '1', 'y': '1', 'z': '1'})

        # Set this logical volume as the world volume
        self.current_geometry_state.world_volume_ref = "World"

        # Recalculate to populate evaluated fields
        self.recalculate_geometry_state()
        
        # Reset history and change tracker
        self.history = []
        self.history_index = -1
        self._clear_change_tracker() # Important for consistency
        self._capture_history_state("New project")

    def load_project_version(self, version_id):
        """Loads a specific project version from its directory."""
        version_filepath = os.path.join(self._get_version_dir(version_id), "version.json")
        with open(version_filepath, 'r') as f:
            json_string = f.read()
        
        self.load_project_from_json_string(json_string)
        self.current_version_id = version_id
        self.is_changed = False
        return True, f"Loaded version {version_id}"
    
    def _get_version_dir(self, version_id):
        """Returns the full path to a specific version directory."""
        project_path = self._get_project_path()
        return os.path.join(project_path, "versions", version_id)
    
    def save_project_version(self, description=""):
        """Saves the current geometry state as a new version."""
        # --- Check to prevent naming a version 'autosave' ---
        if description.replace(' ', '_') == AUTOSAVE_VERSION_ID:
            return None, "Cannot use a reserved name for the version description."
        
        project_path = self._get_project_path()
        versions_path = os.path.join(project_path, "versions")
        os.makedirs(versions_path, exist_ok=True)
        
        # Use a more descriptive name if available
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        version_name = f"{timestamp}_{description.replace(' ', '_')}" if description else timestamp
        
        version_dir = self._get_version_dir(version_name)
        os.makedirs(version_dir)
        
        # Create a subdirectory for future simulation runs
        os.makedirs(os.path.join(version_dir, "sim_runs"), exist_ok=True)

        version_filepath = os.path.join(version_dir, "version.json")
        json_string = self.save_project_to_json_string()
        with open(version_filepath, 'w') as f:
            f.write(json_string)
            
        self.is_changed = False # The project is now saved
        self.current_version_id = version_name # This is now the active version
        return version_name, "Version saved successfully."

    def begin_transaction(self):
        """Starts a transaction, preventing intermediate history captures."""
        if not self._is_transaction_open:
            print("Beginning transaction...")
            self._is_transaction_open = True
            # Store the state *before* the transaction starts, in case we need to revert.
            self._pre_transaction_state = GeometryState.from_dict(self.current_geometry_state.to_dict())

    def end_transaction(self, description=""):
        """Ends a transaction and captures the final state to the history stack."""
        if self._is_transaction_open:
            print("Ending transaction.")
            self._is_transaction_open = False
            self._pre_transaction_state = None
            # Now, capture the single, final state of the entire operation.
            self._capture_history_state(description)

    def abort_transaction(self):
        """Aborts an open transaction and restores the pre-transaction state."""
        if self._is_transaction_open:
            print("Aborting transaction.")
            if self._pre_transaction_state is not None:
                self.current_geometry_state = GeometryState.from_dict(self._pre_transaction_state.to_dict())
                success, error_msg = self.recalculate_geometry_state()
                if not success:
                    print(f"CRITICAL WARNING: Aborted transaction restored an invalid state: {error_msg}")
            self._is_transaction_open = False
            self._pre_transaction_state = None

    def _capture_history_state(self, description=""):
        """Captures the current state for undo/redo."""

        # --- Don't capture state if transaction is open ---
        if self._is_transaction_open:
            # print("Transaction open, skipping intermediate history capture.")
            return # Do nothing if a transaction is in progress
        
        # If we undo and then make a change, invalidate the "redo" stack
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]

        # Use the state's to_dict method for a deep copy
        state_copy = GeometryState.from_dict(self.current_geometry_state.to_dict())
        self.history.append(state_copy)

        # Cap the history size
        if len(self.history) > self.MAX_HISTORY_SIZE:
            self.history.pop(0)
        
        self.history_index = len(self.history) - 1
        #print(f"History captured. Index: {self.history_index}, Size: {len(self.history)}")

        # Mark project as having changes
        self.is_changed = True

    def undo(self):
        """Reverts to the previous state in history and recalculates it."""
        if self.history_index > 0:
            self.history_index -= 1
            # Load the raw state from history
            self.current_geometry_state = GeometryState.from_dict(self.history[self.history_index].to_dict())
            
            # After loading any state, it must be re-evaluated to be valid for rendering.
            success, error_msg = self.recalculate_geometry_state()
            if not success:
                # This would be a serious bug if an undo leads to an invalid state
                print(f"CRITICAL WARNING: Undo operation resulted in an invalid state: {error_msg}")
                return False, f"Undo failed: {error_msg}"

            return True, "Undo successful."
        return False, "Nothing to undo."

    def redo(self):
        """Applies the next state in history and recalculates it."""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            # Load the raw state from history
            self.current_geometry_state = GeometryState.from_dict(self.history[self.history_index].to_dict())

            # After loading any state, it must be re-evaluated.
            success, error_msg = self.recalculate_geometry_state()
            if not success:
                print(f"CRITICAL WARNING: Redo operation resulted in an invalid state: {error_msg}")
                return False, f"Redo failed: {error_msg}"

            return True, "Redo successful."
        return False, "Nothing to redo."

    def _generate_unique_name(self, base_name, existing_names_dict):
        if base_name not in existing_names_dict:
            return base_name
        i = 1
        while f"{base_name}_{i}" in existing_names_dict:
            i += 1
        return f"{base_name}_{i}"

    def _find_step_import_record(self, import_id):
        """Returns (index, record) for a CAD import entry if it exists."""
        if not self.current_geometry_state or not isinstance(import_id, str) or not import_id.strip():
            return None, None

        cad_imports = getattr(self.current_geometry_state, 'cad_imports', None)
        if not isinstance(cad_imports, list):
            return None, None

        for index, cad_import in enumerate(cad_imports):
            if isinstance(cad_import, dict) and cad_import.get('import_id') == import_id:
                return index, cad_import

        return None, None

    def _find_object_name_by_id(self, objects_by_name, object_id):
        """Returns the object name for a given stable object id if present."""
        if not isinstance(objects_by_name, dict) or not isinstance(object_id, str) or not object_id.strip():
            return None

        for object_name, object_value in objects_by_name.items():
            if getattr(object_value, 'id', None) == object_id:
                return object_name

        return None

    def _resolve_logical_volume_name(self, logical_volume_ref):
        """Resolve a logical volume by name or stable id."""
        if not isinstance(logical_volume_ref, str):
            return None

        logical_volume_ref = logical_volume_ref.strip()
        if not logical_volume_ref or not self.current_geometry_state:
            return None

        if logical_volume_ref in self.current_geometry_state.logical_volumes:
            return logical_volume_ref

        return self._find_object_name_by_id(self.current_geometry_state.logical_volumes, logical_volume_ref)

    def _resolve_detector_feature_object_name(self, object_ref, objects_by_name):
        """Resolve a detector-feature object ref that may contain an id and/or name."""
        if not isinstance(object_ref, dict):
            return None

        ref_id = object_ref.get('id')
        if isinstance(ref_id, str):
            resolved_name = self._find_object_name_by_id(objects_by_name, ref_id.strip())
            if resolved_name:
                return resolved_name

        ref_name = object_ref.get('name')
        if isinstance(ref_name, str):
            ref_name = ref_name.strip()
            if ref_name and ref_name in objects_by_name:
                return ref_name

        return None

    @staticmethod
    def _get_detector_feature_object_name_hint(object_ref):
        if not isinstance(object_ref, dict):
            return None

        ref_name = object_ref.get('name')
        if isinstance(ref_name, str):
            ref_name = ref_name.strip()
            if ref_name:
                return ref_name

        return None

    @staticmethod
    def _build_detector_feature_object_ref(obj):
        if obj is None:
            return None

        object_ref = {}
        object_id = getattr(obj, 'id', None)
        object_name = getattr(obj, 'name', None)

        if isinstance(object_id, str) and object_id.strip():
            object_ref['id'] = object_id
        if isinstance(object_name, str) and object_name.strip():
            object_ref['name'] = object_name

        return object_ref or None

    def _find_detector_feature_generated_name(self, object_refs, objects_by_name, *, suffix=None, object_type=None):
        for object_ref in object_refs or []:
            candidate_name = (
                self._resolve_detector_feature_object_name(object_ref, objects_by_name)
                or self._get_detector_feature_object_name_hint(object_ref)
            )
            if not candidate_name or candidate_name not in objects_by_name:
                continue

            candidate_obj = objects_by_name[candidate_name]
            if object_type and getattr(candidate_obj, 'type', None) != object_type:
                continue
            if suffix and not candidate_name.endswith(suffix):
                continue

            return candidate_name

        return None

    def _remove_detector_feature_generated_placements(self, placement_refs):
        if not self.current_geometry_state:
            return

        placement_ids = set()
        placement_names = set()
        for object_ref in placement_refs or []:
            if not isinstance(object_ref, dict):
                continue
            object_id = object_ref.get('id')
            object_name = object_ref.get('name')
            if isinstance(object_id, str) and object_id.strip():
                placement_ids.add(object_id.strip())
            if isinstance(object_name, str) and object_name.strip():
                placement_names.add(object_name.strip())

        if not placement_ids and not placement_names:
            return

        for lv in self.current_geometry_state.logical_volumes.values():
            if lv.content_type != 'physvol' or not isinstance(lv.content, list):
                continue
            lv.content = [
                pv for pv in lv.content
                if pv.id not in placement_ids and pv.name not in placement_names
            ]

    @staticmethod
    def _build_layered_stack_vis_attributes(role):
        role_colors = {
            'absorber': {'r': 0.55, 'g': 0.58, 'b': 0.63, 'a': 0.85},
            'sensor': {'r': 0.18, 'g': 0.68, 'b': 0.78, 'a': 0.75},
            'support': {'r': 0.78, 'g': 0.58, 'b': 0.2, 'a': 0.7},
            'shield': {'r': 0.46, 'g': 0.48, 'b': 0.25, 'a': 0.72},
            'module': {'r': 0.72, 'g': 0.76, 'b': 0.84, 'a': 0.08},
        }
        return {'color': role_colors.get(role, role_colors['module'])}

    def _upsert_detector_feature_generated_solid(self, solid_name, solid_type, raw_parameters):
        state = self.current_geometry_state
        solid = state.solids.get(solid_name)
        if solid is None:
            solid = Solid(solid_name, solid_type, raw_parameters)
            state.add_solid(solid)
        else:
            solid.type = solid_type
            solid.raw_parameters = raw_parameters
        return solid

    def _upsert_detector_feature_generated_logical_volume(
        self,
        lv_name,
        *,
        solid_ref,
        material_ref,
        vis_attributes,
        is_sensitive=False,
    ):
        state = self.current_geometry_state
        lv = state.logical_volumes.get(lv_name)
        if lv is None:
            lv = LogicalVolume(
                lv_name,
                solid_ref,
                material_ref,
                vis_attributes=vis_attributes,
                is_sensitive=is_sensitive,
            )
            state.add_logical_volume(lv)
        else:
            lv.solid_ref = solid_ref
            lv.material_ref = material_ref
            lv.vis_attributes = vis_attributes
            lv.is_sensitive = bool(is_sensitive)

        lv.content_type = 'physvol'
        if not isinstance(lv.content, list):
            lv.content = []
        return lv

    def _get_detector_feature_box_dimensions(self, solid_name, *, label):
        state = self.current_geometry_state
        solid = state.solids.get(solid_name) if state else None
        if solid is None:
            return None, f"{label} solid '{solid_name}' was not found."
        if solid.type != 'box':
            return None, f"{label} currently support only box solids."

        dims = solid._evaluated_parameters or {}
        normalized_dims = {}
        for axis in ('x', 'y', 'z'):
            value = float(dims.get(axis, float('nan')))
            if not math.isfinite(value) or value <= 0.0:
                return None, f"{label} solid '{solid_name}' has invalid evaluated {axis.upper()} size."
            normalized_dims[axis] = value

        return normalized_dims, None

    def _find_detector_feature_generator(self, generator_id):
        if not self.current_geometry_state or not isinstance(generator_id, str) or not generator_id.strip():
            return None, None

        for index, generator_entry in enumerate(self.current_geometry_state.detector_feature_generators):
            if isinstance(generator_entry, dict) and generator_entry.get('generator_id') == generator_id.strip():
                return index, generator_entry

        return None, None

    def get_detector_feature_generator_details(self, generator_name_or_id):
        if not self.current_geometry_state:
            return None
        if not isinstance(generator_name_or_id, str) or not generator_name_or_id.strip():
            return None

        lookup_value = generator_name_or_id.strip()
        _, generator_entry = self._find_detector_feature_generator(lookup_value)
        if generator_entry is not None:
            return deepcopy(generator_entry)

        for candidate_entry in self.current_geometry_state.detector_feature_generators:
            if not isinstance(candidate_entry, dict):
                continue
            candidate_name = candidate_entry.get('name')
            if isinstance(candidate_name, str) and candidate_name.strip() == lookup_value:
                return deepcopy(candidate_entry)

        return None

    def _get_detector_feature_target_logical_volume_names(
        self,
        generator_entry,
        *,
        target_solid_name,
        prior_result_solid_name=None,
    ):
        state = self.current_geometry_state
        target_section = generator_entry.get('target', {}) or {}
        requested_refs = target_section.get('logical_volume_refs', []) or []
        allowed_solid_refs = {target_solid_name}
        if isinstance(prior_result_solid_name, str) and prior_result_solid_name.strip():
            allowed_solid_refs.add(prior_result_solid_name.strip())

        target_lv_names = []
        seen_lv_names = set()

        if requested_refs:
            for object_ref in requested_refs:
                lv_name = self._resolve_detector_feature_object_name(object_ref, state.logical_volumes)
                if not lv_name:
                    requested_name = (
                        self._get_detector_feature_object_name_hint(object_ref)
                        or object_ref.get('id')
                        or '<unknown>'
                    )
                    return None, f"Target logical volume '{requested_name}' was not found."

                if lv_name in seen_lv_names:
                    continue

                lv = state.logical_volumes.get(lv_name)
                if lv is None:
                    return None, f"Target logical volume '{lv_name}' was not found."

                if lv.solid_ref not in allowed_solid_refs:
                    allowed_solid_refs_str = ", ".join(sorted(allowed_solid_refs))
                    return None, (
                        f"Target logical volume '{lv_name}' must reference '{allowed_solid_refs_str}' "
                        "before realization."
                    )

                seen_lv_names.add(lv_name)
                target_lv_names.append(lv_name)

            return target_lv_names, None

        for lv_name, lv in state.logical_volumes.items():
            if lv.solid_ref in allowed_solid_refs and lv_name not in seen_lv_names:
                seen_lv_names.add(lv_name)
                target_lv_names.append(lv_name)

        return target_lv_names, None

    def _prepare_drilled_hole_array_realization(self, generator_entry, *, generator_label):
        state = self.current_geometry_state
        generator_id = generator_entry.get('generator_id')
        generator_name = generator_entry.get('name') or generator_id or 'detector_feature_generator'
        target_section = generator_entry.get('target', {}) or {}
        target_solid_name = self._resolve_detector_feature_object_name(
            target_section.get('solid_ref'),
            state.solids,
        )
        if not target_solid_name:
            requested_name = (
                self._get_detector_feature_object_name_hint(target_section.get('solid_ref'))
                or (target_section.get('solid_ref') or {}).get('id')
                or '<unknown>'
            )
            return None, f"Target solid '{requested_name}' was not found."

        target_solid = state.solids.get(target_solid_name)
        if target_solid is None:
            return None, f"Target solid '{target_solid_name}' was not found."
        if target_solid.type != 'box':
            return None, f"{generator_label} generators currently support only box target solids."

        pattern = generator_entry.get('pattern', {}) or {}
        hole = generator_entry.get('hole', {}) or {}

        if pattern.get('anchor') != 'target_center':
            return None, f"{generator_label} generators currently require anchor 'target_center'."
        if hole.get('shape') != 'cylindrical':
            return None, f"{generator_label} generators currently require cylindrical holes."
        if hole.get('axis') != 'z':
            return None, f"{generator_label} generators currently support only z-axis drilling."
        if hole.get('drill_from') != 'positive_z_face':
            return None, f"{generator_label} generators currently drill only from the positive-z face."

        target_dims = target_solid._evaluated_parameters or {}
        target_depth = float(target_dims.get('z', float('nan')))
        if not math.isfinite(target_depth) or target_depth <= 0.0:
            return None, f"Target solid '{target_solid_name}' has invalid evaluated depth."

        hole_diameter = float(hole.get('diameter_mm') or 0.0)
        hole_depth = float(hole.get('depth_mm') or 0.0)
        if hole_diameter <= 0.0 or hole_depth <= 0.0:
            return None, f"{generator_label} generators require positive hole diameter and depth."

        realization = generator_entry.get('realization', {}) or {}
        prior_result_name = (
            self._resolve_detector_feature_object_name(realization.get('result_solid_ref'), state.solids)
            or self._get_detector_feature_object_name_hint(realization.get('result_solid_ref'))
        )
        prior_generated_solid_refs = (realization.get('generated_object_refs') or {}).get('solid_refs', []) or []

        existing_result_name = None
        if prior_result_name and prior_result_name in state.solids:
            prior_result_solid = state.solids[prior_result_name]
            if prior_result_solid.type == 'boolean':
                existing_result_name = prior_result_name

        existing_cutter_name = None
        for object_ref in prior_generated_solid_refs:
            candidate_name = (
                self._resolve_detector_feature_object_name(object_ref, state.solids)
                or self._get_detector_feature_object_name_hint(object_ref)
            )
            if not candidate_name or candidate_name == prior_result_name or candidate_name not in state.solids:
                continue
            candidate_solid = state.solids[candidate_name]
            if candidate_solid.type == 'tube':
                existing_cutter_name = candidate_name
                break

        cutter_name = existing_cutter_name or self._generate_unique_name(
            f"{generator_name}__cutter",
            state.solids,
        )
        result_name = existing_result_name or self._generate_unique_name(
            f"{generator_name}__result",
            state.solids,
        )

        return {
            'state': state,
            'generator_id': generator_id,
            'generator_name': generator_name,
            'target_solid_name': target_solid_name,
            'pattern': pattern,
            'hole_diameter': hole_diameter,
            'hole_depth': hole_depth,
            'target_depth': target_depth,
            'prior_result_name': prior_result_name,
            'cutter_name': cutter_name,
            'result_name': result_name,
        }, None

    def _realize_drilled_hole_array_with_positions(self, generator_entry, context, hole_positions_xy):
        state = context['state']
        generator_id = context['generator_id']
        generator_name = context['generator_name']
        target_solid_name = context['target_solid_name']
        hole_diameter = context['hole_diameter']
        hole_depth = context['hole_depth']
        target_depth = context['target_depth']
        prior_result_name = context['prior_result_name']
        cutter_name = context['cutter_name']
        result_name = context['result_name']

        def _fmt(value):
            return f"{float(value):.12g}"

        cutter_params = {
            'rmin': '0',
            'rmax': _fmt(hole_diameter / 2.0),
            'z': _fmt(hole_depth),
            'startphi': '0',
            'deltaphi': '360*deg',
        }

        cutter_solid = state.solids.get(cutter_name)
        if cutter_solid is None:
            cutter_solid = Solid(cutter_name, 'tube', cutter_params)
            state.add_solid(cutter_solid)
        else:
            cutter_solid.raw_parameters = cutter_params

        z_center = (target_depth / 2.0) - (hole_depth / 2.0)

        recipe = [{'op': 'base', 'solid_ref': target_solid_name}]
        for x_position, y_position in hole_positions_xy:
            recipe.append({
                'op': 'subtraction',
                'solid_ref': cutter_name,
                'transform': {
                    'position': {
                        'x': _fmt(x_position),
                        'y': _fmt(y_position),
                        'z': _fmt(z_center),
                    },
                },
            })

        result_solid = state.solids.get(result_name)
        if result_solid is None:
            result_solid = Solid(result_name, 'boolean', {'recipe': recipe})
            state.add_solid(result_solid)
        else:
            result_solid.raw_parameters = {'recipe': recipe}

        target_lv_names, error_msg = self._get_detector_feature_target_logical_volume_names(
            generator_entry,
            target_solid_name=target_solid_name,
            prior_result_solid_name=prior_result_name,
        )
        if error_msg:
            return None, error_msg

        touched_logical_volumes = []
        touched_placement_refs = []
        seen_placement_ids = set()
        for lv_name in target_lv_names:
            lv = state.logical_volumes.get(lv_name)
            if lv is None:
                continue
            lv.solid_ref = result_name
            logical_volume_ref = self._build_detector_feature_object_ref(lv)
            if logical_volume_ref:
                touched_logical_volumes.append(logical_volume_ref)

            for pv in self._find_pvs_by_lv_name(lv_name):
                pv_ref = self._build_detector_feature_object_ref(pv)
                if not pv_ref:
                    continue
                pv_ref_id = pv_ref.get('id') or pv_ref.get('name')
                if pv_ref_id in seen_placement_ids:
                    continue
                seen_placement_ids.add(pv_ref_id)
                touched_placement_refs.append(pv_ref)

        generator_entry['realization'] = {
            'mode': 'boolean_subtraction',
            'status': 'generated',
            'result_solid_ref': self._build_detector_feature_object_ref(result_solid),
            'generated_object_refs': {
                'solid_refs': [
                    self._build_detector_feature_object_ref(result_solid),
                    self._build_detector_feature_object_ref(cutter_solid),
                ],
                'logical_volume_refs': touched_logical_volumes,
                'placement_refs': touched_placement_refs,
            },
        }

        return {
            'generator_id': generator_id,
            'generator_name': generator_name,
            'generated_solid_names': [result_name, cutter_name],
            'result_solid_name': result_name,
            'cutter_solid_name': cutter_name,
            'updated_logical_volume_names': target_lv_names,
            'hole_count': len(hole_positions_xy),
        }, None

    def _realize_rectangular_drilled_hole_array(self, generator_entry):
        context, error_msg = self._prepare_drilled_hole_array_realization(
            generator_entry,
            generator_label='Rectangular drilled-hole',
        )
        if error_msg:
            return None, error_msg

        pattern = context['pattern']
        count_x = int(pattern.get('count_x') or 0)
        count_y = int(pattern.get('count_y') or 0)
        pitch_x = float((pattern.get('pitch_mm') or {}).get('x') or 0.0)
        pitch_y = float((pattern.get('pitch_mm') or {}).get('y') or 0.0)
        origin_offset = pattern.get('origin_offset_mm') or {}
        offset_x = float(origin_offset.get('x') or 0.0)
        offset_y = float(origin_offset.get('y') or 0.0)
        if count_x <= 0 or count_y <= 0:
            return None, "Rectangular drilled-hole generators require positive x/y counts."
        if pitch_x <= 0.0 or pitch_y <= 0.0:
            return None, "Rectangular drilled-hole generators require positive x/y pitch values."

        x_origin = -((count_x - 1) * pitch_x) / 2.0 + offset_x
        y_origin = -((count_y - 1) * pitch_y) / 2.0 + offset_y
        hole_positions_xy = []
        for y_index in range(count_y):
            y_position = y_origin + y_index * pitch_y
            for x_index in range(count_x):
                x_position = x_origin + x_index * pitch_x
                hole_positions_xy.append((x_position, y_position))

        return self._realize_drilled_hole_array_with_positions(
            generator_entry,
            context,
            hole_positions_xy,
        )

    def _realize_circular_drilled_hole_array(self, generator_entry):
        context, error_msg = self._prepare_drilled_hole_array_realization(
            generator_entry,
            generator_label='Circular drilled-hole',
        )
        if error_msg:
            return None, error_msg

        pattern = context['pattern']
        count = int(pattern.get('count') or 0)
        radius_mm = float(pattern.get('radius_mm') or 0.0)
        orientation_deg = float(pattern.get('orientation_deg') or 0.0)
        origin_offset = pattern.get('origin_offset_mm') or {}
        offset_x = float(origin_offset.get('x') or 0.0)
        offset_y = float(origin_offset.get('y') or 0.0)
        if count <= 0:
            return None, "Circular drilled-hole generators require a positive hole count."
        if radius_mm <= 0.0:
            return None, "Circular drilled-hole generators require a positive radius."

        angle_step_deg = 360.0 / count
        hole_positions_xy = []
        for index in range(count):
            angle_rad = math.radians(orientation_deg + (index * angle_step_deg))
            hole_positions_xy.append((
                offset_x + (radius_mm * math.cos(angle_rad)),
                offset_y + (radius_mm * math.sin(angle_rad)),
            ))

        return self._realize_drilled_hole_array_with_positions(
            generator_entry,
            context,
            hole_positions_xy,
        )

    def _realize_layered_detector_stack(self, generator_entry):
        state = self.current_geometry_state
        generator_id = generator_entry.get('generator_id')
        generator_name = generator_entry.get('name') or generator_id or 'detector_feature_generator'
        target_section = generator_entry.get('target', {}) or {}
        stack = generator_entry.get('stack', {}) or {}
        layers = generator_entry.get('layers', {}) or {}
        realization = generator_entry.get('realization', {}) or {}
        generated_refs = realization.get('generated_object_refs', {}) or {}

        parent_lv_name = self._resolve_detector_feature_object_name(
            target_section.get('parent_logical_volume_ref'),
            state.logical_volumes,
        )
        if not parent_lv_name:
            requested_name = (
                self._get_detector_feature_object_name_hint(target_section.get('parent_logical_volume_ref'))
                or (target_section.get('parent_logical_volume_ref') or {}).get('id')
                or '<unknown>'
            )
            return None, f"Parent logical volume '{requested_name}' was not found."

        parent_lv = state.logical_volumes.get(parent_lv_name)
        if parent_lv is None:
            return None, f"Parent logical volume '{parent_lv_name}' was not found."
        if parent_lv.content_type != 'physvol':
            return None, (
                f"Layered detector-stack generators require parent logical volume "
                f"'{parent_lv_name}' to use standard placements."
            )
        if not self._logical_volume_is_instantiated_in_scene(parent_lv_name):
            return None, (
                f"Layered detector-stack generators require parent logical volume "
                f"'{parent_lv_name}' to already be placed in the live scene so generated modules are visible."
            )

        if stack.get('anchor') != 'target_center':
            return None, "Layered detector-stack generators currently require anchor 'target_center'."

        module_size = stack.get('module_size_mm') or {}
        module_size_x = float(module_size.get('x') or 0.0)
        module_size_y = float(module_size.get('y') or 0.0)
        module_count = int(stack.get('module_count') or 0)
        module_pitch_mm = float(stack.get('module_pitch_mm') or 0.0)
        origin_offset = stack.get('origin_offset_mm') or {}
        offset_x = float(origin_offset.get('x') or 0.0)
        offset_y = float(origin_offset.get('y') or 0.0)
        offset_z = float(origin_offset.get('z') or 0.0)
        if module_size_x <= 0.0 or module_size_y <= 0.0:
            return None, "Layered detector-stack generators require positive module X/Y sizes."
        if module_count <= 0:
            return None, "Layered detector-stack generators require a positive module count."
        if module_pitch_mm <= 0.0:
            return None, "Layered detector-stack generators require a positive module pitch."

        layer_order = ('absorber', 'sensor', 'support')
        layer_specs = []
        total_thickness_mm = 0.0
        for role in layer_order:
            layer_entry = layers.get(role) or {}
            material_ref = str(layer_entry.get('material_ref') or '').strip()
            thickness_mm = float(layer_entry.get('thickness_mm') or 0.0)
            if not material_ref:
                return None, f"Layered detector-stack generators require a material for layer '{role}'."
            if thickness_mm <= 0.0:
                return None, f"Layered detector-stack generators require positive thickness for layer '{role}'."

            layer_specs.append({
                'role': role,
                'material_ref': material_ref,
                'thickness_mm': thickness_mm,
                'is_sensitive': bool(layer_entry.get('is_sensitive', role == 'sensor')),
            })
            total_thickness_mm += thickness_mm

        if module_pitch_mm + 1e-9 < total_thickness_mm:
            return None, (
                f"Layered detector-stack generator '{generator_name}' requires module_pitch_mm "
                "to be at least the total layer thickness."
            )

        prior_result_name = (
            self._resolve_detector_feature_object_name(realization.get('result_solid_ref'), state.solids)
            or self._get_detector_feature_object_name_hint(realization.get('result_solid_ref'))
        )
        prior_solid_refs = generated_refs.get('solid_refs', []) or []
        prior_lv_refs = generated_refs.get('logical_volume_refs', []) or []
        prior_placement_refs = generated_refs.get('placement_refs', []) or []

        module_solid_name = self._find_detector_feature_generated_name(
            prior_solid_refs,
            state.solids,
            suffix='__module_solid',
            object_type='box',
        )
        if module_solid_name is None and prior_result_name in state.solids:
            prior_result_solid = state.solids[prior_result_name]
            if prior_result_solid.type == 'box':
                module_solid_name = prior_result_name
        if module_solid_name is None:
            module_solid_name = self._generate_unique_name(
                f"{generator_name}__module_solid",
                state.solids,
            )

        layer_solid_names = {}
        for role in layer_order:
            layer_solid_name = self._find_detector_feature_generated_name(
                prior_solid_refs,
                state.solids,
                suffix=f"__{role}_solid",
                object_type='box',
            )
            if layer_solid_name is None:
                layer_solid_name = self._generate_unique_name(
                    f"{generator_name}__{role}_solid",
                    state.solids,
                )
            layer_solid_names[role] = layer_solid_name

        module_lv_name = self._find_detector_feature_generated_name(
            prior_lv_refs,
            state.logical_volumes,
            suffix='__module_lv',
        )
        if module_lv_name is None:
            module_lv_name = self._generate_unique_name(
                f"{generator_name}__module_lv",
                state.logical_volumes,
            )

        layer_lv_names = {}
        for role in layer_order:
            layer_lv_name = self._find_detector_feature_generated_name(
                prior_lv_refs,
                state.logical_volumes,
                suffix=f"__{role}_lv",
            )
            if layer_lv_name is None:
                layer_lv_name = self._generate_unique_name(
                    f"{generator_name}__{role}_lv",
                    state.logical_volumes,
                )
            layer_lv_names[role] = layer_lv_name

        self._remove_detector_feature_generated_placements(prior_placement_refs)

        def _fmt(value):
            return f"{float(value):.12g}"

        module_solid = self._upsert_detector_feature_generated_solid(
            module_solid_name,
            'box',
            {
                'x': _fmt(module_size_x),
                'y': _fmt(module_size_y),
                'z': _fmt(total_thickness_mm),
            },
        )

        layer_solids = {}
        layer_lvs = {}
        for layer_spec in layer_specs:
            role = layer_spec['role']
            layer_solids[role] = self._upsert_detector_feature_generated_solid(
                layer_solid_names[role],
                'box',
                {
                    'x': _fmt(module_size_x),
                    'y': _fmt(module_size_y),
                    'z': _fmt(layer_spec['thickness_mm']),
                },
            )
            layer_lvs[role] = self._upsert_detector_feature_generated_logical_volume(
                layer_lv_names[role],
                solid_ref=layer_solid_names[role],
                material_ref=layer_spec['material_ref'],
                vis_attributes=self._build_layered_stack_vis_attributes(role),
                is_sensitive=layer_spec['is_sensitive'],
            )

        module_lv = self._upsert_detector_feature_generated_logical_volume(
            module_lv_name,
            solid_ref=module_solid_name,
            material_ref=parent_lv.material_ref,
            vis_attributes=self._build_layered_stack_vis_attributes('module'),
            is_sensitive=False,
        )
        module_lv.content = []

        layer_placements = []
        z_cursor = -total_thickness_mm / 2.0
        for layer_index, layer_spec in enumerate(layer_specs, start=1):
            role = layer_spec['role']
            z_center = z_cursor + (layer_spec['thickness_mm'] / 2.0)
            layer_pv = PhysicalVolumePlacement(
                name=f"{generator_name}__{role}_pv",
                volume_ref=layer_lv_names[role],
                parent_lv_name=module_lv_name,
                copy_number_expr=str(layer_index),
                position_val_or_ref={
                    'x': '0',
                    'y': '0',
                    'z': _fmt(z_center),
                },
                rotation_val_or_ref={'x': '0', 'y': '0', 'z': '0'},
                scale_val_or_ref={'x': '1', 'y': '1', 'z': '1'},
            )
            module_lv.content.append(layer_pv)
            layer_placements.append(layer_pv)
            z_cursor += layer_spec['thickness_mm']

        parent_copy_start = self._get_next_copy_number(parent_lv)
        module_placements = []
        z_origin = offset_z - (((module_count - 1) * module_pitch_mm) / 2.0)
        for index in range(module_count):
            module_pv = PhysicalVolumePlacement(
                name=f"{generator_name}__module_{index + 1}_pv",
                volume_ref=module_lv_name,
                parent_lv_name=parent_lv_name,
                copy_number_expr=str(parent_copy_start + index),
                position_val_or_ref={
                    'x': _fmt(offset_x),
                    'y': _fmt(offset_y),
                    'z': _fmt(z_origin + (index * module_pitch_mm)),
                },
                rotation_val_or_ref={'x': '0', 'y': '0', 'z': '0'},
                scale_val_or_ref={'x': '1', 'y': '1', 'z': '1'},
            )
            module_placements.append(module_pv)

        parent_lv.content.extend(module_placements)

        layer_detail_parts = [
            f"{layer_spec['role']}={_fmt(layer_spec['thickness_mm'])} mm {layer_spec['material_ref']}"
            for layer_spec in layer_specs
        ]

        generator_entry['realization'] = {
            'mode': 'layered_stack',
            'status': 'generated',
            'result_solid_ref': self._build_detector_feature_object_ref(module_solid),
            'generated_object_refs': {
                'solid_refs': [
                    self._build_detector_feature_object_ref(module_solid),
                    *[
                        self._build_detector_feature_object_ref(layer_solids[role])
                        for role in layer_order
                    ],
                ],
                'logical_volume_refs': [
                    self._build_detector_feature_object_ref(module_lv),
                    *[
                        self._build_detector_feature_object_ref(layer_lvs[role])
                        for role in layer_order
                    ],
                ],
                'placement_refs': [
                    *[
                        self._build_detector_feature_object_ref(module_pv)
                        for module_pv in module_placements
                    ],
                    *[
                        self._build_detector_feature_object_ref(layer_pv)
                        for layer_pv in layer_placements
                    ],
                ],
            },
        }

        return {
            'generator_id': generator_id,
            'generator_name': generator_name,
            'generated_solid_names': [
                module_solid_name,
                *[layer_solid_names[role] for role in layer_order],
            ],
            'generated_logical_volume_names': [
                module_lv_name,
                *[layer_lv_names[role] for role in layer_order],
            ],
            'generated_placement_names': [
                *[module_pv.name for module_pv in module_placements],
                *[layer_pv.name for layer_pv in layer_placements],
            ],
            'result_solid_name': module_solid_name,
            'module_logical_volume_name': module_lv_name,
            'parent_logical_volume_name': parent_lv_name,
            'module_count': module_count,
            'layer_count': len(layer_specs),
            'total_thickness_mm': total_thickness_mm,
            'layer_summary': ", ".join(layer_detail_parts),
        }, None

    def _realize_tiled_sensor_array(self, generator_entry):
        state = self.current_geometry_state
        generator_id = generator_entry.get('generator_id')
        generator_name = generator_entry.get('name') or generator_id or 'detector_feature_generator'
        target_section = generator_entry.get('target', {}) or {}
        array = generator_entry.get('array', {}) or {}
        sensor = generator_entry.get('sensor', {}) or {}
        realization = generator_entry.get('realization', {}) or {}
        generated_refs = realization.get('generated_object_refs', {}) or {}

        parent_lv_name = self._resolve_detector_feature_object_name(
            target_section.get('parent_logical_volume_ref'),
            state.logical_volumes,
        )
        if not parent_lv_name:
            requested_name = (
                self._get_detector_feature_object_name_hint(target_section.get('parent_logical_volume_ref'))
                or (target_section.get('parent_logical_volume_ref') or {}).get('id')
                or '<unknown>'
            )
            return None, f"Parent logical volume '{requested_name}' was not found."

        parent_lv = state.logical_volumes.get(parent_lv_name)
        if parent_lv is None:
            return None, f"Parent logical volume '{parent_lv_name}' was not found."
        if parent_lv.content_type != 'physvol':
            return None, (
                f"Tiled sensor-array generators require parent logical volume "
                f"'{parent_lv_name}' to use standard placements."
            )
        if not self._logical_volume_is_instantiated_in_scene(parent_lv_name):
            return None, (
                f"Tiled sensor-array generators require parent logical volume "
                f"'{parent_lv_name}' to already be placed in the live scene so generated sensors are visible."
            )

        if array.get('anchor') != 'target_center':
            return None, "Tiled sensor-array generators currently require anchor 'target_center'."

        count_x = int(array.get('count_x') or 0)
        count_y = int(array.get('count_y') or 0)
        pitch = array.get('pitch_mm') or {}
        pitch_x = float(pitch.get('x') or 0.0)
        pitch_y = float(pitch.get('y') or 0.0)
        origin_offset = array.get('origin_offset_mm') or {}
        offset_x = float(origin_offset.get('x') or 0.0)
        offset_y = float(origin_offset.get('y') or 0.0)
        offset_z = float(origin_offset.get('z') or 0.0)
        if count_x <= 0 or count_y <= 0:
            return None, "Tiled sensor-array generators require positive x/y counts."
        if pitch_x <= 0.0 or pitch_y <= 0.0:
            return None, "Tiled sensor-array generators require positive x/y pitch values."

        sensor_size = sensor.get('size_mm') or {}
        sensor_size_x = float(sensor_size.get('x') or 0.0)
        sensor_size_y = float(sensor_size.get('y') or 0.0)
        sensor_thickness = float(sensor.get('thickness_mm') or 0.0)
        sensor_material_ref = str(sensor.get('material_ref') or '').strip()
        sensor_sensitive = bool(sensor.get('is_sensitive', True))
        if sensor_size_x <= 0.0 or sensor_size_y <= 0.0:
            return None, "Tiled sensor-array generators require positive sensor X/Y sizes."
        if sensor_thickness <= 0.0:
            return None, "Tiled sensor-array generators require positive sensor thickness."
        if not sensor_material_ref:
            return None, "Tiled sensor-array generators require a sensor material."
        if pitch_x + 1e-9 < sensor_size_x or pitch_y + 1e-9 < sensor_size_y:
            return None, (
                f"Tiled sensor-array generator '{generator_name}' requires x/y pitch to be at least "
                "the generated sensor size to avoid overlapping placements."
            )

        prior_result_name = (
            self._resolve_detector_feature_object_name(realization.get('result_solid_ref'), state.solids)
            or self._get_detector_feature_object_name_hint(realization.get('result_solid_ref'))
        )
        prior_solid_refs = generated_refs.get('solid_refs', []) or []
        prior_lv_refs = generated_refs.get('logical_volume_refs', []) or []
        prior_placement_refs = generated_refs.get('placement_refs', []) or []

        sensor_solid_name = self._find_detector_feature_generated_name(
            prior_solid_refs,
            state.solids,
            suffix='__sensor_solid',
            object_type='box',
        )
        if sensor_solid_name is None and prior_result_name in state.solids:
            prior_result_solid = state.solids[prior_result_name]
            if prior_result_solid.type == 'box':
                sensor_solid_name = prior_result_name
        if sensor_solid_name is None:
            sensor_solid_name = self._generate_unique_name(
                f"{generator_name}__sensor_solid",
                state.solids,
            )

        sensor_lv_name = self._find_detector_feature_generated_name(
            prior_lv_refs,
            state.logical_volumes,
            suffix='__sensor_lv',
        )
        if sensor_lv_name is None:
            sensor_lv_name = self._generate_unique_name(
                f"{generator_name}__sensor_lv",
                state.logical_volumes,
            )

        self._remove_detector_feature_generated_placements(prior_placement_refs)

        def _fmt(value):
            return f"{float(value):.12g}"

        sensor_solid = self._upsert_detector_feature_generated_solid(
            sensor_solid_name,
            'box',
            {
                'x': _fmt(sensor_size_x),
                'y': _fmt(sensor_size_y),
                'z': _fmt(sensor_thickness),
            },
        )

        sensor_lv = self._upsert_detector_feature_generated_logical_volume(
            sensor_lv_name,
            solid_ref=sensor_solid_name,
            material_ref=sensor_material_ref,
            vis_attributes=self._build_layered_stack_vis_attributes('sensor'),
            is_sensitive=sensor_sensitive,
        )
        sensor_lv.content = []

        parent_copy_start = self._get_next_copy_number(parent_lv)
        x_origin = offset_x - (((count_x - 1) * pitch_x) / 2.0)
        y_origin = offset_y - (((count_y - 1) * pitch_y) / 2.0)
        sensor_placements = []
        placement_index = 0
        for row_index in range(count_y):
            y_position = y_origin + (row_index * pitch_y)
            for column_index in range(count_x):
                x_position = x_origin + (column_index * pitch_x)
                placement_index += 1
                sensor_pv = PhysicalVolumePlacement(
                    name=f"{generator_name}__sensor_r{row_index + 1}_c{column_index + 1}_pv",
                    volume_ref=sensor_lv_name,
                    parent_lv_name=parent_lv_name,
                    copy_number_expr=str(parent_copy_start + placement_index - 1),
                    position_val_or_ref={
                        'x': _fmt(x_position),
                        'y': _fmt(y_position),
                        'z': _fmt(offset_z),
                    },
                    rotation_val_or_ref={'x': '0', 'y': '0', 'z': '0'},
                    scale_val_or_ref={'x': '1', 'y': '1', 'z': '1'},
                )
                sensor_placements.append(sensor_pv)

        parent_lv.content.extend(sensor_placements)

        generator_entry['realization'] = {
            'mode': 'placement_array',
            'status': 'generated',
            'result_solid_ref': self._build_detector_feature_object_ref(sensor_solid),
            'generated_object_refs': {
                'solid_refs': [
                    self._build_detector_feature_object_ref(sensor_solid),
                ],
                'logical_volume_refs': [
                    self._build_detector_feature_object_ref(sensor_lv),
                ],
                'placement_refs': [
                    self._build_detector_feature_object_ref(sensor_pv)
                    for sensor_pv in sensor_placements
                ],
            },
        }

        return {
            'generator_id': generator_id,
            'generator_name': generator_name,
            'generated_solid_names': [sensor_solid_name],
            'generated_logical_volume_names': [sensor_lv_name],
            'generated_placement_names': [sensor_pv.name for sensor_pv in sensor_placements],
            'result_solid_name': sensor_solid_name,
            'sensor_logical_volume_name': sensor_lv_name,
            'parent_logical_volume_name': parent_lv_name,
            'sensor_count': len(sensor_placements),
            'count_x': count_x,
            'count_y': count_y,
            'pitch_x_mm': pitch_x,
            'pitch_y_mm': pitch_y,
            'sensor_size_x_mm': sensor_size_x,
            'sensor_size_y_mm': sensor_size_y,
            'sensor_thickness_mm': sensor_thickness,
        }, None

    def _realize_support_rib_array(self, generator_entry):
        state = self.current_geometry_state
        generator_id = generator_entry.get('generator_id')
        generator_name = generator_entry.get('name') or generator_id or 'detector_feature_generator'
        target_section = generator_entry.get('target', {}) or {}
        array = generator_entry.get('array', {}) or {}
        rib = generator_entry.get('rib', {}) or {}
        realization = generator_entry.get('realization', {}) or {}
        generated_refs = realization.get('generated_object_refs', {}) or {}

        parent_lv_name = self._resolve_detector_feature_object_name(
            target_section.get('parent_logical_volume_ref'),
            state.logical_volumes,
        )
        if not parent_lv_name:
            requested_name = (
                self._get_detector_feature_object_name_hint(target_section.get('parent_logical_volume_ref'))
                or (target_section.get('parent_logical_volume_ref') or {}).get('id')
                or '<unknown>'
            )
            return None, f"Parent logical volume '{requested_name}' was not found."

        parent_lv = state.logical_volumes.get(parent_lv_name)
        if parent_lv is None:
            return None, f"Parent logical volume '{parent_lv_name}' was not found."
        if parent_lv.content_type != 'physvol':
            return None, (
                f"Support-rib generators require parent logical volume "
                f"'{parent_lv_name}' to use standard placements."
            )
        if not self._logical_volume_is_instantiated_in_scene(parent_lv_name):
            return None, (
                f"Support-rib generators require parent logical volume "
                f"'{parent_lv_name}' to already be placed in the live scene so generated ribs are visible."
            )

        if array.get('anchor') != 'target_center':
            return None, "Support-rib generators currently require anchor 'target_center'."

        repeat_axis = str(array.get('axis') or '').strip()
        count = int(array.get('count') or 0)
        linear_pitch_mm = float(array.get('linear_pitch_mm') or 0.0)
        origin_offset = array.get('origin_offset_mm') or {}
        offset_x = float(origin_offset.get('x') or 0.0)
        offset_y = float(origin_offset.get('y') or 0.0)
        offset_z = float(origin_offset.get('z') or 0.0)
        rib_width_mm = float(rib.get('width_mm') or 0.0)
        rib_height_mm = float(rib.get('height_mm') or 0.0)
        rib_material_ref = str(rib.get('material_ref') or '').strip()
        rib_sensitive = bool(rib.get('is_sensitive', False))
        if repeat_axis not in {'x', 'y'}:
            return None, "Support-rib generators require repeat axis 'x' or 'y'."
        if count <= 0:
            return None, "Support-rib generators require a positive rib count."
        if linear_pitch_mm <= 0.0:
            return None, "Support-rib generators require a positive rib pitch."
        if rib_width_mm <= 0.0:
            return None, "Support-rib generators require a positive rib width."
        if rib_height_mm <= 0.0:
            return None, "Support-rib generators require a positive rib height."
        if not rib_material_ref:
            return None, "Support-rib generators require a rib material."
        if count > 1 and linear_pitch_mm + 1e-9 < rib_width_mm:
            return None, (
                f"Support-rib generator '{generator_name}' requires pitch to be at least "
                "the rib width to avoid overlapping placements."
            )

        parent_box_dims, error_msg = self._get_detector_feature_box_dimensions(
            parent_lv.solid_ref,
            label="Support-rib generators",
        )
        if error_msg:
            return None, error_msg

        prior_result_name = (
            self._resolve_detector_feature_object_name(realization.get('result_solid_ref'), state.solids)
            or self._get_detector_feature_object_name_hint(realization.get('result_solid_ref'))
        )
        prior_solid_refs = generated_refs.get('solid_refs', []) or []
        prior_lv_refs = generated_refs.get('logical_volume_refs', []) or []
        prior_placement_refs = generated_refs.get('placement_refs', []) or []

        rib_solid_name = self._find_detector_feature_generated_name(
            prior_solid_refs,
            state.solids,
            suffix='__rib_solid',
            object_type='box',
        )
        if rib_solid_name is None and prior_result_name in state.solids:
            prior_result_solid = state.solids[prior_result_name]
            if prior_result_solid.type == 'box':
                rib_solid_name = prior_result_name
        if rib_solid_name is None:
            rib_solid_name = self._generate_unique_name(
                f"{generator_name}__rib_solid",
                state.solids,
            )

        rib_lv_name = self._find_detector_feature_generated_name(
            prior_lv_refs,
            state.logical_volumes,
            suffix='__rib_lv',
        )
        if rib_lv_name is None:
            rib_lv_name = self._generate_unique_name(
                f"{generator_name}__rib_lv",
                state.logical_volumes,
            )

        self._remove_detector_feature_generated_placements(prior_placement_refs)

        def _fmt(value):
            return f"{float(value):.12g}"

        rib_size_x = rib_width_mm if repeat_axis == 'x' else parent_box_dims['x']
        rib_size_y = parent_box_dims['y'] if repeat_axis == 'x' else rib_width_mm

        rib_solid = self._upsert_detector_feature_generated_solid(
            rib_solid_name,
            'box',
            {
                'x': _fmt(rib_size_x),
                'y': _fmt(rib_size_y),
                'z': _fmt(rib_height_mm),
            },
        )

        rib_lv = self._upsert_detector_feature_generated_logical_volume(
            rib_lv_name,
            solid_ref=rib_solid_name,
            material_ref=rib_material_ref,
            vis_attributes=self._build_layered_stack_vis_attributes('support'),
            is_sensitive=rib_sensitive,
        )
        rib_lv.content = []

        parent_copy_start = self._get_next_copy_number(parent_lv)
        axis_origin = (
            offset_x - (((count - 1) * linear_pitch_mm) / 2.0)
            if repeat_axis == 'x'
            else offset_y - (((count - 1) * linear_pitch_mm) / 2.0)
        )
        rib_placements = []
        for index in range(count):
            axis_value = axis_origin + (index * linear_pitch_mm)
            position = {
                'x': _fmt(axis_value if repeat_axis == 'x' else offset_x),
                'y': _fmt(offset_y if repeat_axis == 'x' else axis_value),
                'z': _fmt(offset_z),
            }
            rib_pv = PhysicalVolumePlacement(
                name=f"{generator_name}__rib_{index + 1}_pv",
                volume_ref=rib_lv_name,
                parent_lv_name=parent_lv_name,
                copy_number_expr=str(parent_copy_start + index),
                position_val_or_ref=position,
                rotation_val_or_ref={'x': '0', 'y': '0', 'z': '0'},
                scale_val_or_ref={'x': '1', 'y': '1', 'z': '1'},
            )
            rib_placements.append(rib_pv)

        parent_lv.content.extend(rib_placements)

        generator_entry['realization'] = {
            'mode': 'placement_array',
            'status': 'generated',
            'result_solid_ref': self._build_detector_feature_object_ref(rib_solid),
            'generated_object_refs': {
                'solid_refs': [
                    self._build_detector_feature_object_ref(rib_solid),
                ],
                'logical_volume_refs': [
                    self._build_detector_feature_object_ref(rib_lv),
                ],
                'placement_refs': [
                    self._build_detector_feature_object_ref(rib_pv)
                    for rib_pv in rib_placements
                ],
            },
        }

        return {
            'generator_id': generator_id,
            'generator_name': generator_name,
            'generated_solid_names': [rib_solid_name],
            'generated_logical_volume_names': [rib_lv_name],
            'generated_placement_names': [rib_pv.name for rib_pv in rib_placements],
            'result_solid_name': rib_solid_name,
            'rib_logical_volume_name': rib_lv_name,
            'parent_logical_volume_name': parent_lv_name,
            'rib_count': count,
            'repeat_axis': repeat_axis,
            'pitch_mm': linear_pitch_mm,
            'rib_width_mm': rib_width_mm,
            'rib_height_mm': rib_height_mm,
        }, None

    def _realize_channel_cut_array(self, generator_entry):
        state = self.current_geometry_state
        generator_id = generator_entry.get('generator_id')
        generator_name = generator_entry.get('name') or generator_id or 'detector_feature_generator'
        target_section = generator_entry.get('target', {}) or {}
        array = generator_entry.get('array', {}) or {}
        channel = generator_entry.get('channel', {}) or {}
        realization = generator_entry.get('realization', {}) or {}
        generated_refs = realization.get('generated_object_refs', {}) or {}

        target_solid_name = self._resolve_detector_feature_object_name(
            target_section.get('solid_ref'),
            state.solids,
        )
        if not target_solid_name:
            requested_name = (
                self._get_detector_feature_object_name_hint(target_section.get('solid_ref'))
                or (target_section.get('solid_ref') or {}).get('id')
                or '<unknown>'
            )
            return None, f"Target solid '{requested_name}' was not found."

        target_box_dims, error_msg = self._get_detector_feature_box_dimensions(
            target_solid_name,
            label="Channel-cut generators",
        )
        if error_msg:
            return None, error_msg

        if array.get('anchor') != 'target_center':
            return None, "Channel-cut generators currently require anchor 'target_center'."

        repeat_axis = str(array.get('axis') or '').strip()
        count = int(array.get('count') or 0)
        linear_pitch_mm = float(array.get('linear_pitch_mm') or 0.0)
        origin_offset = array.get('origin_offset_mm') or {}
        offset_x = float(origin_offset.get('x') or 0.0)
        offset_y = float(origin_offset.get('y') or 0.0)
        channel_width_mm = float(channel.get('width_mm') or 0.0)
        channel_depth_mm = float(channel.get('depth_mm') or 0.0)
        if repeat_axis not in {'x', 'y'}:
            return None, "Channel-cut generators require repeat axis 'x' or 'y'."
        if count <= 0:
            return None, "Channel-cut generators require a positive channel count."
        if linear_pitch_mm <= 0.0:
            return None, "Channel-cut generators require a positive channel pitch."
        if channel_width_mm <= 0.0:
            return None, "Channel-cut generators require a positive channel width."
        if channel_depth_mm <= 0.0:
            return None, "Channel-cut generators require a positive channel depth."
        if count > 1 and linear_pitch_mm + 1e-9 < channel_width_mm:
            return None, (
                f"Channel-cut generator '{generator_name}' requires pitch to be at least "
                "the channel width to avoid overlapping cuts."
            )

        prior_result_name = (
            self._resolve_detector_feature_object_name(realization.get('result_solid_ref'), state.solids)
            or self._get_detector_feature_object_name_hint(realization.get('result_solid_ref'))
        )
        prior_generated_solid_refs = generated_refs.get('solid_refs', []) or []

        existing_result_name = None
        if prior_result_name and prior_result_name in state.solids:
            prior_result_solid = state.solids[prior_result_name]
            if prior_result_solid.type == 'boolean':
                existing_result_name = prior_result_name

        cutter_name = self._find_detector_feature_generated_name(
            prior_generated_solid_refs,
            state.solids,
            suffix='__channel_cutter',
            object_type='box',
        )
        if cutter_name is None:
            cutter_name = self._generate_unique_name(
                f"{generator_name}__channel_cutter",
                state.solids,
            )
        result_name = existing_result_name or self._generate_unique_name(
            f"{generator_name}__result",
            state.solids,
        )

        def _fmt(value):
            return f"{float(value):.12g}"

        cutter_size_x = channel_width_mm if repeat_axis == 'x' else target_box_dims['x']
        cutter_size_y = target_box_dims['y'] if repeat_axis == 'x' else channel_width_mm
        cutter_solid = state.solids.get(cutter_name)
        cutter_params = {
            'x': _fmt(cutter_size_x),
            'y': _fmt(cutter_size_y),
            'z': _fmt(channel_depth_mm),
        }
        if cutter_solid is None:
            cutter_solid = Solid(cutter_name, 'box', cutter_params)
            state.add_solid(cutter_solid)
        else:
            cutter_solid.type = 'box'
            cutter_solid.raw_parameters = cutter_params

        z_center = (target_box_dims['z'] / 2.0) - (channel_depth_mm / 2.0)
        axis_origin = (
            offset_x - (((count - 1) * linear_pitch_mm) / 2.0)
            if repeat_axis == 'x'
            else offset_y - (((count - 1) * linear_pitch_mm) / 2.0)
        )

        recipe = [{'op': 'base', 'solid_ref': target_solid_name}]
        for index in range(count):
            axis_value = axis_origin + (index * linear_pitch_mm)
            recipe.append({
                'op': 'subtraction',
                'solid_ref': cutter_name,
                'transform': {
                    'position': {
                        'x': _fmt(axis_value if repeat_axis == 'x' else offset_x),
                        'y': _fmt(offset_y if repeat_axis == 'x' else axis_value),
                        'z': _fmt(z_center),
                    },
                },
            })

        result_solid = state.solids.get(result_name)
        if result_solid is None:
            result_solid = Solid(result_name, 'boolean', {'recipe': recipe})
            state.add_solid(result_solid)
        else:
            result_solid.type = 'boolean'
            result_solid.raw_parameters = {'recipe': recipe}

        target_lv_names, error_msg = self._get_detector_feature_target_logical_volume_names(
            generator_entry,
            target_solid_name=target_solid_name,
            prior_result_solid_name=prior_result_name,
        )
        if error_msg:
            return None, error_msg
        if target_lv_names and not any(
            self._logical_volume_is_instantiated_in_scene(lv_name)
            for lv_name in target_lv_names
        ):
            target_label = (
                f"logical volume '{target_lv_names[0]}'"
                if len(target_lv_names) == 1
                else "logical volumes"
            )
            return None, (
                "Channel-cut generators require at least one targeted "
                f"{target_label} to already be placed in the live scene so generated cuts are visible."
            )

        touched_logical_volumes = []
        touched_placement_refs = []
        seen_placement_ids = set()
        for lv_name in target_lv_names:
            lv = state.logical_volumes.get(lv_name)
            if lv is None:
                continue
            lv.solid_ref = result_name
            logical_volume_ref = self._build_detector_feature_object_ref(lv)
            if logical_volume_ref:
                touched_logical_volumes.append(logical_volume_ref)

            for pv in self._find_pvs_by_lv_name(lv_name):
                pv_ref = self._build_detector_feature_object_ref(pv)
                if not pv_ref:
                    continue
                pv_ref_id = pv_ref.get('id') or pv_ref.get('name')
                if pv_ref_id in seen_placement_ids:
                    continue
                seen_placement_ids.add(pv_ref_id)
                touched_placement_refs.append(pv_ref)

        generator_entry['realization'] = {
            'mode': 'boolean_subtraction',
            'status': 'generated',
            'result_solid_ref': self._build_detector_feature_object_ref(result_solid),
            'generated_object_refs': {
                'solid_refs': [
                    self._build_detector_feature_object_ref(result_solid),
                    self._build_detector_feature_object_ref(cutter_solid),
                ],
                'logical_volume_refs': touched_logical_volumes,
                'placement_refs': touched_placement_refs,
            },
        }

        return {
            'generator_id': generator_id,
            'generator_name': generator_name,
            'generated_solid_names': [result_name, cutter_name],
            'result_solid_name': result_name,
            'cutter_solid_name': cutter_name,
            'updated_logical_volume_names': target_lv_names,
            'channel_count': count,
            'repeat_axis': repeat_axis,
            'pitch_mm': linear_pitch_mm,
        }, None

    def _realize_annular_shield_sleeve(self, generator_entry):
        state = self.current_geometry_state
        generator_id = generator_entry.get('generator_id')
        generator_name = generator_entry.get('name') or generator_id or 'detector_feature_generator'
        target_section = generator_entry.get('target', {}) or {}
        shield = generator_entry.get('shield', {}) or {}
        realization = generator_entry.get('realization', {}) or {}
        generated_refs = realization.get('generated_object_refs', {}) or {}

        parent_lv_name = self._resolve_detector_feature_object_name(
            target_section.get('parent_logical_volume_ref'),
            state.logical_volumes,
        )
        if not parent_lv_name:
            requested_name = (
                self._get_detector_feature_object_name_hint(target_section.get('parent_logical_volume_ref'))
                or (target_section.get('parent_logical_volume_ref') or {}).get('id')
                or '<unknown>'
            )
            return None, f"Parent logical volume '{requested_name}' was not found."

        parent_lv = state.logical_volumes.get(parent_lv_name)
        if parent_lv is None:
            return None, f"Parent logical volume '{parent_lv_name}' was not found."
        if parent_lv.content_type != 'physvol':
            return None, (
                f"Annular shield-sleeve generators require parent logical volume "
                f"'{parent_lv_name}' to use standard placements."
            )
        if not self._logical_volume_is_instantiated_in_scene(parent_lv_name):
            return None, (
                f"Annular shield-sleeve generators require parent logical volume "
                f"'{parent_lv_name}' to already be placed in the live scene so generated shields are visible."
            )

        if shield.get('anchor') != 'target_center':
            return None, "Annular shield-sleeve generators currently require anchor 'target_center'."

        inner_radius_mm = float(shield.get('inner_radius_mm') or 0.0)
        outer_radius_mm = float(shield.get('outer_radius_mm') or 0.0)
        length_mm = float(shield.get('length_mm') or 0.0)
        material_ref = str(shield.get('material_ref') or '').strip()
        origin_offset = shield.get('origin_offset_mm') or {}
        offset_x = float(origin_offset.get('x') or 0.0)
        offset_y = float(origin_offset.get('y') or 0.0)
        offset_z = float(origin_offset.get('z') or 0.0)

        if inner_radius_mm <= 0.0:
            return None, "Annular shield-sleeve generators require a positive inner radius."
        if outer_radius_mm <= inner_radius_mm:
            return None, (
                f"Annular shield-sleeve generator '{generator_name}' requires outer_radius_mm "
                "to be greater than inner_radius_mm."
            )
        if length_mm <= 0.0:
            return None, "Annular shield-sleeve generators require a positive axial length."
        if not material_ref:
            return None, "Annular shield-sleeve generators require a shield material."

        prior_result_name = (
            self._resolve_detector_feature_object_name(realization.get('result_solid_ref'), state.solids)
            or self._get_detector_feature_object_name_hint(realization.get('result_solid_ref'))
        )
        prior_solid_refs = generated_refs.get('solid_refs', []) or []
        prior_lv_refs = generated_refs.get('logical_volume_refs', []) or []
        prior_placement_refs = generated_refs.get('placement_refs', []) or []

        shield_solid_name = self._find_detector_feature_generated_name(
            prior_solid_refs,
            state.solids,
            suffix='__shield_solid',
            object_type='tube',
        )
        if shield_solid_name is None and prior_result_name in state.solids:
            prior_result_solid = state.solids[prior_result_name]
            if prior_result_solid.type == 'tube':
                shield_solid_name = prior_result_name
        if shield_solid_name is None:
            shield_solid_name = self._generate_unique_name(
                f"{generator_name}__shield_solid",
                state.solids,
            )

        shield_lv_name = self._find_detector_feature_generated_name(
            prior_lv_refs,
            state.logical_volumes,
            suffix='__shield_lv',
        )
        if shield_lv_name is None:
            shield_lv_name = self._generate_unique_name(
                f"{generator_name}__shield_lv",
                state.logical_volumes,
            )

        self._remove_detector_feature_generated_placements(prior_placement_refs)

        def _fmt(value):
            return f"{float(value):.12g}"

        shield_solid = self._upsert_detector_feature_generated_solid(
            shield_solid_name,
            'tube',
            {
                'rmin': _fmt(inner_radius_mm),
                'rmax': _fmt(outer_radius_mm),
                'z': _fmt(length_mm),
                'startphi': '0',
                'deltaphi': '360',
            },
        )

        shield_lv = self._upsert_detector_feature_generated_logical_volume(
            shield_lv_name,
            solid_ref=shield_solid_name,
            material_ref=material_ref,
            vis_attributes=self._build_layered_stack_vis_attributes('shield'),
            is_sensitive=False,
        )
        shield_lv.content = []

        shield_pv = PhysicalVolumePlacement(
            name=f"{generator_name}__shield_pv",
            volume_ref=shield_lv_name,
            parent_lv_name=parent_lv_name,
            copy_number_expr=str(self._get_next_copy_number(parent_lv)),
            position_val_or_ref={
                'x': _fmt(offset_x),
                'y': _fmt(offset_y),
                'z': _fmt(offset_z),
            },
            rotation_val_or_ref={'x': '0', 'y': '0', 'z': '0'},
            scale_val_or_ref={'x': '1', 'y': '1', 'z': '1'},
        )
        parent_lv.content.append(shield_pv)

        generator_entry['realization'] = {
            'mode': 'placement_array',
            'status': 'generated',
            'result_solid_ref': self._build_detector_feature_object_ref(shield_solid),
            'generated_object_refs': {
                'solid_refs': [
                    self._build_detector_feature_object_ref(shield_solid),
                ],
                'logical_volume_refs': [
                    self._build_detector_feature_object_ref(shield_lv),
                ],
                'placement_refs': [
                    self._build_detector_feature_object_ref(shield_pv),
                ],
            },
        }

        return {
            'generator_id': generator_id,
            'generator_name': generator_name,
            'generated_solid_names': [shield_solid_name],
            'generated_logical_volume_names': [shield_lv_name],
            'generated_placement_names': [shield_pv.name],
            'result_solid_name': shield_solid_name,
            'shield_logical_volume_name': shield_lv_name,
            'parent_logical_volume_name': parent_lv_name,
            'inner_radius_mm': inner_radius_mm,
            'outer_radius_mm': outer_radius_mm,
            'length_mm': length_mm,
            'material_ref': material_ref,
        }, None

    def _realize_detector_feature_generator_entry(self, generator_entry):
        generator_type = generator_entry.get('generator_type')
        if generator_type == 'rectangular_drilled_hole_array':
            return self._realize_rectangular_drilled_hole_array(generator_entry)
        if generator_type == 'circular_drilled_hole_array':
            return self._realize_circular_drilled_hole_array(generator_entry)
        if generator_type == 'layered_detector_stack':
            return self._realize_layered_detector_stack(generator_entry)
        if generator_type == 'tiled_sensor_array':
            return self._realize_tiled_sensor_array(generator_entry)
        if generator_type == 'support_rib_array':
            return self._realize_support_rib_array(generator_entry)
        if generator_type == 'channel_cut_array':
            return self._realize_channel_cut_array(generator_entry)
        if generator_type == 'annular_shield_sleeve':
            return self._realize_annular_shield_sleeve(generator_entry)

        return None, (
            f"Detector feature generator type '{generator_type}' is not supported for realization."
        )

    def upsert_detector_feature_generator(self, raw_entry, *, realize_now=True):
        """Create or update one saved detector-feature-generator contract."""
        if not self.current_geometry_state:
            return None, None, "No project loaded."
        if not isinstance(raw_entry, dict):
            return None, None, "Detector feature generator payload must be an object."

        requested_generator_id = raw_entry.get('generator_id')
        existing_index, existing_entry = self._find_detector_feature_generator(requested_generator_id)

        candidate_entry = deepcopy(raw_entry)
        if existing_entry is not None:
            candidate_entry.setdefault('generator_id', existing_entry.get('generator_id'))
            candidate_entry.setdefault('generator_type', existing_entry.get('generator_type'))
            candidate_entry.setdefault('enabled', existing_entry.get('enabled', True))
            if 'target' not in candidate_entry:
                candidate_entry['target'] = deepcopy(existing_entry.get('target', {}))
            if 'pattern' not in candidate_entry:
                candidate_entry['pattern'] = deepcopy(existing_entry.get('pattern', {}))
            if 'stack' not in candidate_entry:
                candidate_entry['stack'] = deepcopy(existing_entry.get('stack', {}))
            if 'array' not in candidate_entry:
                candidate_entry['array'] = deepcopy(existing_entry.get('array', {}))
            if 'layers' not in candidate_entry:
                candidate_entry['layers'] = deepcopy(existing_entry.get('layers', {}))
            if 'sensor' not in candidate_entry:
                candidate_entry['sensor'] = deepcopy(existing_entry.get('sensor', {}))
            if 'shield' not in candidate_entry:
                candidate_entry['shield'] = deepcopy(existing_entry.get('shield', {}))
            if 'hole' not in candidate_entry:
                candidate_entry['hole'] = deepcopy(existing_entry.get('hole', {}))
            if 'realization' not in candidate_entry:
                candidate_entry['realization'] = deepcopy(existing_entry.get('realization', {}))

        try:
            normalized_entry = normalize_detector_feature_generator_entry(candidate_entry)
        except ValueError as exc:
            return None, None, str(exc)

        self.begin_transaction()
        realization_result = None
        try:
            if existing_index is None:
                self.current_geometry_state.detector_feature_generators.append(normalized_entry)
                generator_entry = self.current_geometry_state.detector_feature_generators[-1]
            else:
                self.current_geometry_state.detector_feature_generators[existing_index] = normalized_entry
                generator_entry = self.current_geometry_state.detector_feature_generators[existing_index]

            if realize_now:
                success, error_msg = self.recalculate_geometry_state()
                if not success:
                    raise ValueError(error_msg)

                realization_result, error_msg = self._realize_detector_feature_generator_entry(generator_entry)
                if error_msg:
                    raise ValueError(error_msg)

                self.changed_object_ids['solids'].update(
                    realization_result.get('generated_solid_names', [])
                )

                success, error_msg = self.recalculate_geometry_state()
                if not success:
                    raise ValueError(error_msg)
            else:
                realization_mode = (
                    'layered_stack'
                    if generator_entry.get('generator_type') == 'layered_detector_stack'
                    else 'placement_array'
                    if generator_entry.get('generator_type') in {'tiled_sensor_array', 'support_rib_array', 'annular_shield_sleeve'}
                    else 'boolean_subtraction'
                )
                generator_entry['realization'] = {
                    'mode': realization_mode,
                    'status': 'spec_only',
                    'result_solid_ref': None,
                    'generated_object_refs': {
                        'solid_refs': [],
                        'logical_volume_refs': [],
                        'placement_refs': [],
                    },
                }

            action_verb = 'Saved and realized' if realize_now else 'Saved'
            description = generator_entry.get('name') or generator_entry.get('generator_id') or 'detector feature generator'
        except Exception as exc:
            self.abort_transaction()
            return None, None, str(exc)

        self.end_transaction(f"{action_verb} detector feature generator '{description}'")
        return deepcopy(generator_entry), realization_result, None

    def realize_detector_feature_generator(self, generator_id):
        """Materialize a saved detector-feature-generator spec into concrete geometry."""
        if not self.current_geometry_state:
            return None, "No project loaded."

        generator_index, generator_entry = self._find_detector_feature_generator(generator_id)
        if generator_entry is None:
            return None, f"Detector feature generator '{generator_id}' was not found."
        if not bool(generator_entry.get('enabled', True)):
            return None, f"Detector feature generator '{generator_id}' is disabled."

        success, error_msg = self.recalculate_geometry_state()
        if not success:
            return None, error_msg

        self.begin_transaction()
        try:
            result, error_msg = self._realize_detector_feature_generator_entry(generator_entry)
            if error_msg:
                raise ValueError(error_msg)

            self.changed_object_ids['solids'].update(result.get('generated_solid_names', []))

            success, error_msg = self.recalculate_geometry_state()
            if not success:
                raise ValueError(error_msg)
        except Exception as exc:
            self.abort_transaction()
            return None, str(exc)

        description = generator_entry.get('name') or generator_entry.get('generator_id') or f"generator #{generator_index}"
        self.end_transaction(f"Realized detector feature generator '{description}'")
        return result, None

    def _snapshot_step_import_annotations(self, cad_import_record):
        """Captures user-facing annotations that should survive a supported reimport."""
        if not self.current_geometry_state or not isinstance(cad_import_record, dict):
            return {
                'logical_volumes': {},
                'sources': {},
                'ui_groups': {},
            }

        object_ids = cad_import_record.get('created_object_ids', {}) or {}
        imported_pv_ids = {
            object_id
            for object_id in (object_ids.get('placement_ids', []) or [])
            if isinstance(object_id, str) and object_id.strip()
        }

        snapshot = {
            'logical_volumes': {},
            'sources': {},
            'ui_groups': {},
        }

        imported_names_by_type = {
            'solid': {
                name
                for object_id in object_ids.get('solid_ids', []) or []
                if (name := self._find_object_name_by_id(self.current_geometry_state.solids, object_id))
            },
            'logical_volume': {
                name
                for object_id in object_ids.get('logical_volume_ids', []) or []
                if (name := self._find_object_name_by_id(self.current_geometry_state.logical_volumes, object_id))
            },
            'assembly': {
                name
                for object_id in object_ids.get('assembly_ids', []) or []
                if (name := self._find_object_name_by_id(self.current_geometry_state.assemblies, object_id))
            },
        }

        for object_id in object_ids.get('logical_volume_ids', []) or []:
            lv_name = self._find_object_name_by_id(self.current_geometry_state.logical_volumes, object_id)
            if not lv_name:
                continue
            lv = self.current_geometry_state.logical_volumes.get(lv_name)
            if not lv:
                continue
            snapshot['logical_volumes'][lv_name] = {
                'material_ref': lv.material_ref,
                'is_sensitive': lv.is_sensitive,
                'vis_attributes': deepcopy(lv.vis_attributes),
            }

        for source in self.current_geometry_state.sources.values():
            linked_pv_id = getattr(source, 'volume_link_id', None)
            if linked_pv_id not in imported_pv_ids:
                continue
            snapshot['sources'][source.id] = {
                'volume_link_name': getattr(self._find_pv_by_id(linked_pv_id), 'name', None),
            }

        for group_type, group_list in getattr(self.current_geometry_state, 'ui_groups', {}).items():
            imported_names = imported_names_by_type.get(group_type, set())
            if not imported_names or not isinstance(group_list, list):
                continue

            preserved_groups = []
            for group in group_list:
                if not isinstance(group, dict):
                    continue
                members = group.get('members', [])
                if any(member in imported_names for member in members if isinstance(member, str)):
                    preserved_groups.append(deepcopy(group))

            if preserved_groups:
                snapshot['ui_groups'][group_type] = preserved_groups

        return snapshot

    def _sync_linked_source_to_pv(self, source, pv, force_confine_name=True):
        """Updates a source so it stays bound to the supplied physical volume."""
        if not source or not pv:
            return

        global_pos, global_rot_rad = self._calculate_global_transform(pv)
        source.position = {
            'x': str(global_pos['x']),
            'y': str(global_pos['y']),
            'z': str(global_pos['z']),
        }
        source.rotation = {
            'x': str(global_rot_rad['x']),
            'y': str(global_rot_rad['y']),
            'z': str(global_rot_rad['z']),
        }
        if force_confine_name or not source.confine_to_pv:
            source.confine_to_pv = pv.name
        source.volume_link_id = pv.id

        lv = self.current_geometry_state.logical_volumes.get(pv.volume_ref)
        if lv:
            solid = self.current_geometry_state.solids.get(lv.solid_ref)
            if solid:
                p = solid._evaluated_parameters
                cmds = source.gps_commands

                # Clear any old shape-specific confinement keys before applying the new shape.
                for key in [
                    'pos/shape', 'pos/radius', 'pos/halfx', 'pos/halfy', 'pos/halfz',
                    'pos/sigma_x', 'pos/sigma_y', 'pos/sigma_r', 'pos/paralp',
                    'pos/parthe', 'pos/parphi'
                ]:
                    cmds.pop(key, None)

                MARGIN = 0.001  # mm
                cmds['pos/type'] = 'Volume'
                if solid.type in ['box']:
                    cmds['pos/shape'] = 'Box'
                    cmds['pos/halfx'] = f"{max(0, p.get('x', 0) / 2 - MARGIN)} mm"
                    cmds['pos/halfy'] = f"{max(0, p.get('y', 0) / 2 - MARGIN)} mm"
                    cmds['pos/halfz'] = f"{max(0, p.get('z', 0) / 2 - MARGIN)} mm"
                elif solid.type in ['tube', 'cylinder', 'tubs']:
                    cmds['pos/shape'] = 'Cylinder'
                    cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                    cmds['pos/halfz'] = f"{max(0, p.get('z', 0) / 2 - MARGIN)} mm"
                elif solid.type in ['sphere', 'orb']:
                    cmds['pos/shape'] = 'Sphere'
                    cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                else:
                    cmds['pos/shape'] = 'Sphere'
                    cmds['pos/radius'] = '50 mm'

        source._evaluated_position = global_pos
        source._evaluated_rotation = global_rot_rad

    def _restore_step_import_annotations(self, annotation_snapshot):
        """Reapplies preserved annotations after a STEP reimport has replaced geometry."""
        if not self.current_geometry_state or not isinstance(annotation_snapshot, dict):
            return

        for lv_name, lv_snapshot in (annotation_snapshot.get('logical_volumes') or {}).items():
            lv = self.current_geometry_state.logical_volumes.get(lv_name)
            if not lv or not isinstance(lv_snapshot, dict):
                continue

            material_ref = _normalize_step_import_object_name(lv_snapshot.get('material_ref'))
            if material_ref is not None:
                lv.material_ref = material_ref

            if 'is_sensitive' in lv_snapshot:
                lv.is_sensitive = bool(lv_snapshot.get('is_sensitive'))

            if lv_snapshot.get('vis_attributes') is not None:
                lv.vis_attributes = deepcopy(lv_snapshot.get('vis_attributes'))

        for source_id, source_snapshot in (annotation_snapshot.get('sources') or {}).items():
            if not isinstance(source_snapshot, dict):
                continue

            source = next(
                (candidate for candidate in self.current_geometry_state.sources.values() if candidate.id == source_id),
                None,
            )
            if not source:
                continue

            linked_name = _normalize_step_import_object_name(source_snapshot.get('volume_link_name'))
            if not linked_name:
                continue

            linked_pv = self._find_pv_by_name(linked_name)
            if not linked_pv:
                continue

            self._sync_linked_source_to_pv(source, linked_pv)

        for group_type, preserved_groups in (annotation_snapshot.get('ui_groups') or {}).items():
            live_groups = self.current_geometry_state.ui_groups.get(group_type)
            if not isinstance(live_groups, list):
                continue

            current_names = {
                'solid': set(self.current_geometry_state.solids.keys()),
                'logical_volume': set(self.current_geometry_state.logical_volumes.keys()),
                'assembly': set(self.current_geometry_state.assemblies.keys()),
            }.get(group_type, set())

            for preserved_group in preserved_groups:
                if not isinstance(preserved_group, dict):
                    continue

                group_name = preserved_group.get('name')
                if not isinstance(group_name, str) or not group_name.strip():
                    continue

                live_group = next((group for group in live_groups if group.get('name') == group_name), None)
                if not live_group:
                    continue

                live_group['members'] = [
                    member
                    for member in preserved_group.get('members', [])
                    if isinstance(member, str) and member.strip() and member in current_names
                ]

    def _delete_step_import_subsystem(self, cad_import_record):
        """Deletes all objects and groups recorded for a STEP import."""
        if not isinstance(cad_import_record, dict):
            return False, "Invalid STEP import provenance record."

        object_ids = cad_import_record.get('created_object_ids', {})
        if not isinstance(object_ids, dict):
            return False, "STEP import provenance record is missing created object ids."

        deletion_specs = []
        seen_specs = set()
        for object_id in object_ids.get('placement_ids', []) or []:
            if not isinstance(object_id, str) or not object_id.strip():
                continue
            spec = ('physical_volume', object_id.strip())
            if spec in seen_specs:
                continue
            seen_specs.add(spec)
            deletion_specs.append({'type': 'physical_volume', 'id': object_id.strip()})

        if deletion_specs:
            success, error_msg = self.delete_objects_batch(deletion_specs)
            if not success:
                return False, error_msg

        deletion_specs = []
        seen_specs = set()
        for object_type, ids_key in (
            ('solid', 'solid_ids'),
            ('logical_volume', 'logical_volume_ids'),
            ('assembly', 'assembly_ids'),
        ):
            for object_id in object_ids.get(ids_key, []) or []:
                if not isinstance(object_id, str) or not object_id.strip():
                    continue
                resolved_id = object_id.strip()
                if object_type == 'solid':
                    resolved_id = self._find_object_name_by_id(self.current_geometry_state.solids, resolved_id)
                elif object_type == 'logical_volume':
                    resolved_id = self._find_object_name_by_id(self.current_geometry_state.logical_volumes, resolved_id)
                elif object_type == 'assembly':
                    resolved_id = self._find_object_name_by_id(self.current_geometry_state.assemblies, resolved_id)

                if resolved_id is None:
                    return False, f"Could not resolve imported {object_type} id '{object_id}' in the current project."

                spec = (object_type, resolved_id)
                if spec in seen_specs:
                    continue
                seen_specs.add(spec)
                deletion_specs.append({'type': object_type, 'id': resolved_id})

        if deletion_specs:
            success, error_msg = self.delete_objects_batch(deletion_specs)
            if not success:
                return False, error_msg

        group_names = cad_import_record.get('created_group_names', {})
        if isinstance(group_names, dict):
            for group_type in ('solid', 'logical_volume', 'assembly'):
                group_name = group_names.get(group_type)
                if isinstance(group_name, str) and group_name.strip():
                    self.delete_group(group_type, group_name.strip())

        return True, None

    def _get_next_copy_number(self, parent_lv: LogicalVolume):
        """Finds the highest copy number among children and returns the next one."""
        # Check content_type and iterate through the correct list
        if parent_lv.content_type != 'physvol' or not parent_lv.content:
            return 1
        
        max_copy_no = 0
        for pv in parent_lv.content:
            if pv.copy_number > max_copy_no:
                max_copy_no = pv.copy_number
        return max_copy_no + 1

    def get_summarized_context(self) -> str:
        """Returns a compact string summary of the geometry for AI context."""
        state = self.current_geometry_state
        summary = [f"Project: {self.project_name}", f"World Volume: {state.world_volume_ref}"]
        
        defines = list(state.defines.keys())
        if defines:
            summary.append(f"Available Variables (Defines): {', '.join(defines[:30])}" + ("..." if len(defines) > 30 else ""))
        else:
            summary.append("Available Variables (Defines): (none defined yet)")
        
        if state.materials:
            summary.append(f"Materials: {', '.join(list(state.materials.keys()))}")
            
        if state.logical_volumes:
            lv_info = []
            for name, lv in list(state.logical_volumes.items())[:30]:
                lv_info.append(f"{name}({lv.solid_ref})")
            summary.append(f"Logical Volumes: {', '.join(lv_info)}" + ("..." if len(state.logical_volumes) > 30 else ""))
            
        if state.assemblies:
            summary.append(f"Assemblies: {', '.join(list(state.assemblies.keys()))}")
            
        if state.sources:
            summary.append(f"Sources: {', '.join(list(state.sources.keys()))}")

        return "\n".join(summary)

    def recalculate_geometry_state(self):
        """
        This is the core evaluation engine for the entire project.
        Recalculates defines, then material properties, then solid parameters,
        and finally placement transforms, respecting all dependencies.
        """
        if not self.current_geometry_state:
            return False, "No project state to calculate."

        state = self.current_geometry_state
        evaluator = self.expression_evaluator
        evaluator.clear_symbols() # Clear old symbols

        # Helper function for evaluating transforms ##
        def evaluate_transform_part(part_data, default_val, rotation=False):

            # Negate Euler angles for rotations
            rotation_factor = 1
            if(rotation): rotation_factor = -1

            if isinstance(part_data, str): # It's a reference to a define
                return evaluator.get_symbol(part_data, default_val)
            elif isinstance(part_data, dict): # It's a dict of expressions
                evaluated_dict = {}
                for axis, raw_expr in part_data.items():
                    try:
                        # Check if it's already a number
                        if isinstance(raw_expr, (int, float)):
                            evaluated_dict[axis] = raw_expr*rotation_factor
                        else:
                            evaluated_dict[axis] = evaluator.evaluate(str(raw_expr))[1]*rotation_factor
                    except Exception:
                        evaluated_dict[axis] = default_val.get(axis, 0)
                return evaluated_dict
            return default_val

        def evaluate_param_dimension_part(raw_value, owner_name, path):
            """Recursively evaluate parameterised dimension payloads."""
            if isinstance(raw_value, dict):
                return {
                    key: evaluate_param_dimension_part(
                        value,
                        owner_name,
                        f"{path}.{key}" if path else key,
                    )
                    for key, value in raw_value.items()
                }
            if isinstance(raw_value, list):
                return [
                    evaluate_param_dimension_part(
                        item,
                        owner_name,
                        f"{path}[{index}]" if path else f"[{index}]",
                    )
                    for index, item in enumerate(raw_value)
                ]
            if isinstance(raw_value, (int, float)):
                return float(raw_value)

            try:
                return float(evaluator.evaluate(str(raw_value))[1])
            except Exception as e:
                label = path or "parameter"
                print(f"Warning: Could not eval param dimension '{label}' for '{owner_name}': {e}")
                return 0.0
        
        # --- Stage 1: Iteratively resolve all defines ---
        unresolved_defines = list(state.defines.values())
        max_passes = len(unresolved_defines) + 2
        for _ in range(max_passes):
            if not unresolved_defines: break
            
            resolved_this_pass = False
            still_unresolved = []
            for define_obj in unresolved_defines:
                try:
                    # For compound types, evaluate each axis expression.
                    if define_obj.type in ['position', 'rotation', 'scale']:
                        val_dict = {}
                        raw_dict = define_obj.raw_expression
                        # We handle units on the GDML side by multiplying in the expression string now
                        # but we still need to apply the default unit from the parent tag if it exists.
                        unit_str = define_obj.unit
                        for axis in ['x', 'y', 'z']:
                            if axis in raw_dict:
                                expr_to_eval = str(raw_dict[axis])
                                # If a unit is defined on the parent tag, apply it
                                if unit_str:
                                    expr_to_eval = f"({expr_to_eval}) * {unit_str}"
                                _, val = evaluator.evaluate(expr_to_eval)
                                val_dict[axis] = val

                                # NOTE: Account for a difference in rotation angle sense in THREE.js and GDML
                                if(define_obj.type == 'rotation'): val_dict[axis] *= -1

                        # Set define value and add to symbol table
                        define_obj.value = val_dict
                        evaluator.add_symbol(define_obj.name, val_dict)

                    elif define_obj.type == 'matrix':
                        raw_dict = define_obj.raw_expression
                        coldim = int(evaluator.evaluate(str(raw_dict['coldim']))[1])
                        
                        evaluated_values = [evaluator.evaluate(str(v))[1] for v in raw_dict['values']]
                        define_obj.value = evaluated_values # Store the flat list of numbers

                        # Now, expand the matrix into the symbol table like Geant4 does
                        if coldim <= 0:
                            raise ValueError("Matrix coldim must be > 0")
                        if len(evaluated_values) % coldim != 0:
                            raise ValueError("Number of values is not a multiple of coldim")

                        if len(evaluated_values) == coldim or coldim == 1: # 1D array
                             for i, val in enumerate(evaluated_values):
                                evaluator.add_symbol(f"{define_obj.name}_{i}", val)
                        else: # 2D array
                            num_rows = len(evaluated_values) // coldim
                            for r in range(num_rows):
                                for c in range(coldim):
                                    evaluator.add_symbol(f"{define_obj.name}_{r}_{c}", evaluated_values[r * coldim + c])

                    else: # constant, quantity, expression
                        expr_to_eval = str(define_obj.raw_expression)
                        unit_str = define_obj.unit
                        if unit_str:
                             expr_to_eval = f"({expr_to_eval}) * {unit_str}"
                        _, val = evaluator.evaluate(expr_to_eval)

                        # Set define value and add to symbol table
                        define_obj.value = val
                        evaluator.add_symbol(define_obj.name, val)

                    resolved_this_pass = True

                except (NameError, KeyError, TypeError):
                    still_unresolved.append(define_obj) # Depends on another define, try again next pass
                except Exception as e:
                    print(f"Error evaluating define '{define_obj.name}': {e}. Setting value to None.")
                    define_obj.value = None
                    resolved_this_pass = True # Consider it "resolved" to avoid infinite loops

            if not resolved_this_pass and still_unresolved:
                unresolved_names = [d.name for d in unresolved_defines]
                return False, f"Could not resolve defines (circular dependency or missing variable): {unresolved_names}"
            unresolved_defines = still_unresolved
            
        if unresolved_defines:
            return False, f"Could not resolve all defines. Unresolved: {[d.name for d in unresolved_defines]}"

        # --- Stage 2: Evaluate Material properties (Z, A, density) ---
        material_errors = []
        for material in state.materials.values():
            if material.Z_expr:
                success, value = evaluator.evaluate(str(material.Z_expr), verbose=False)
                if success:
                    material._evaluated_Z = value
                else:
                    material_errors.append(f"{material.name}.Z: {value}")
            if material.A_expr:
                success, value = evaluator.evaluate(str(material.A_expr), verbose=False)
                if success:
                    material._evaluated_A = value
                else:
                    material_errors.append(f"{material.name}.A: {value}")
            if material.density_expr:
                success, value = evaluator.evaluate(str(material.density_expr), verbose=False)
                if success:
                    material._evaluated_density = value
                else:
                    material_errors.append(f"{material.name}.density: {value}")

        if material_errors:
            return False, "Invalid material expression(s): " + "; ".join(material_errors)


        # --- Stage 3: Evaluate and NORMALIZE solid parameters ---
        for solid in state.solids.values():
            solid._evaluated_parameters = {}
            raw_params = solid.raw_parameters
            
            default_lunit = raw_params.get('lunit')
            default_aunit = raw_params.get('aunit')

            length_attrs = ['x', 'y', 'z', 'rmin', 'rmax', 'r', 'dx', 'dy', 'dz', 'dx1', 'dx2', 'dy1', 'y2', 'rtor', 'ax', 'by', 'cz', 'zcut1', 'zcut2', 'zmax', 'zcut', 'rlo', 'rhi', 'rmin1', 'rmax1', 'rmin2', 'rmax2', 'x1', 'x2', 'y1', 'x3', 'x4']
            angle_attrs = ['startphi', 'deltaphi', 'starttheta', 'deltatheta', 'alpha', 'theta', 'phi', 'inst', 'outst', 'PhiTwist', 'alpha1', 'alpha2', 'Alph', 'Theta', 'Phi', 'twistedangle']

            # First, evaluate all expressions into a temporary dictionary
            temp_eval_params = {}
            for key, raw_expr in raw_params.items():
                if key in ['lunit', 'aunit']: continue
                
                # Handle "scale" key for scaledSolid
                if key == 'scale' and isinstance(raw_expr, dict):
                    evaluated_scale = {}
                    for axis, axis_expr in raw_expr.items():
                        try:
                            evaluated_scale[axis] = evaluator.evaluate(str(axis_expr))[1]
                        except Exception as e:
                            print(f"Warning: Could not eval scale param '{axis}' for solid '{solid.name}': {e}")
                            evaluated_scale[axis] = 1.0 # Default to 1 on failure
                    temp_eval_params[key] = evaluated_scale
                # Handle "solid_ref" key for scaledSolid: just pass it along
                elif key == 'solid_ref' and isinstance(raw_expr, str):
                    temp_eval_params[key] = raw_expr
                elif isinstance(raw_expr, (str, int, float)):

                    # Add default units to expression
                    expr_to_eval = str(raw_expr)
                    if key in length_attrs and default_lunit:
                        expr_to_eval = f"({expr_to_eval}) * {default_lunit}"
                    elif key in angle_attrs and default_aunit:
                        expr_to_eval = f"({expr_to_eval}) * {default_aunit}"

                    try:
                        temp_eval_params[key] = evaluator.evaluate(expr_to_eval)[1]
                    except Exception as e:
                        print(f"Warning: Could not eval solid param '{key}' for solid '{solid.name}' with expression '{expr_to_eval}': {e}")
                        temp_eval_params[key] = float('nan')
                else:
                    temp_eval_params[key] = raw_expr

            # Second pass for normalization ##
            p = temp_eval_params
            ep = solid._evaluated_parameters

            solid_type = solid.type
            if solid_type == 'scaledSolid':
                # For scaled solids, the evaluated params are the scale dict and the solid_ref
                ep['scale'] = p.get('scale', {'x': 1.0, 'y': 1.0, 'z': 1.0})
                ep['solid_ref'] = p.get('solid_ref')

            elif solid_type == 'reflectedSolid':
                ep['solid_ref'] = p.get('solid_ref')
                transform = p.get('transform', {})
                ep['transform'] = {
                    '_evaluated_position': evaluate_transform_part(transform.get('position'), {'x': 0, 'y': 0, 'z': 0}, rotation=False),
                    '_evaluated_rotation': evaluate_transform_part(transform.get('rotation'), {'x': 0, 'y': 0, 'z': 0}, rotation=True),
                    '_evaluated_scale': evaluate_transform_part(transform.get('scale'), {'x': 1, 'y': 1, 'z': 1}, rotation=False)
                }

            elif solid_type == 'box':
                ep['x'] = p.get('x', 0)
                ep['y'] = p.get('y', 0)
                ep['z'] = p.get('z', 0)
            
            elif solid_type == 'tube':
                ep['rmin'] = p.get('rmin', 0)
                ep['rmax'] = p.get('rmax', 10)
                ep['z'] = p.get('z', 20)
                ep['startphi'] = p.get('startphi', 0)
                ep['deltaphi'] = p.get('deltaphi', 2 * math.pi) # Default is a full circle

            elif solid_type == 'cone':
                ep['rmin1'] = p.get('rmin1', 0)
                ep['rmax1'] = p.get('rmax1', 10)
                ep['rmin2'] = p.get('rmin2', 0)
                ep['rmax2'] = p.get('rmax2', 10)
                ep['z']     = p.get('z', 0)
                ep['startphi'] = p.get('startphi', 0)
                ep['deltaphi'] = p.get('deltaphi', 2 * math.pi)

            elif solid_type == 'sphere':
                ep['rmin'] = p.get('rmin', 0)
                ep['rmax'] = p.get('rmax', 10)
                ep['startphi'] = p.get('startphi', 0)
                ep['deltaphi'] = p.get('deltaphi', 2 * math.pi)
                ep['starttheta'] = p.get('starttheta', 0)
                ep['deltatheta'] = p.get('deltatheta', math.pi)

            elif solid_type == 'trd':
                ep['dx1'] = p.get('x1', 0) / 2.0
                ep['dx2'] = p.get('x2', 0) / 2.0
                ep['dy1'] = p.get('y1', 0) / 2.0
                ep['dy2'] = p.get('y2', 0) / 2.0
                ep['dz'] = p.get('z', 0) / 2.0

            elif solid.type == 'para':
                ep['x'] = p.get('x', 0)
                ep['y'] = p.get('y', 0)
                ep['z'] = p.get('z', 0)
                ep['alpha'] = p.get('alpha', 0)
                ep['theta'] = p.get('theta', 0)
                ep['phi'] = p.get('phi', 0)
            
            elif solid.type == 'hype':
                 ep['z'] = p.get('z', 0)
                 ep['rmin'] = p.get('rmin', 0)
                 ep['rmax'] = p.get('rmax', 0)
                 ep['inst'] = p.get('inst', 0)
                 ep['outst'] = p.get('outst', 0)

            elif solid_type == 'trap':
                ep['z'] = p.get('z', 0) / 2.0
                ep['theta'] = p.get('theta', 0)
                ep['phi'] = p.get('phi', 0)
                ep['y1'] = p.get('y1', 0) / 2.0
                ep['x1'] = p.get('x1', 0) / 2.0
                ep['x2'] = p.get('x2', 0) / 2.0
                ep['alpha1'] = p.get('alpha1', 0)
                ep['y2'] = p.get('y2', 0) / 2.0
                ep['x3'] = p.get('x3', 0) / 2.0
                ep['x4'] = p.get('x4', 0) / 2.0
                ep['alpha2'] = p.get('alpha2', 0)
                
            elif solid_type == 'twistedbox':
                ep['PhiTwist'] = p.get('PhiTwist', 0)
                ep['x'] = p.get('x', 0) / 2.0
                ep['y'] = p.get('y', 0) / 2.0
                ep['z'] = p.get('z', 0) / 2.0
            
            elif solid_type == 'twistedtrd':
                ep['PhiTwist'] = p.get('PhiTwist', 0)
                ep['x1'] = p.get('x1', 0) / 2.0
                ep['x2'] = p.get('x2', 0) / 2.0
                ep['y1'] = p.get('y1', 0) / 2.0
                ep['y2'] = p.get('y2', 0) / 2.0
                ep['z'] = p.get('z', 0) / 2.0

            elif solid_type == 'twistedtrap':
                ep['PhiTwist'] = p.get('PhiTwist', 0)
                ep['z'] = p.get('z', 0)
                ep['Theta'] = p.get('Theta', 0)
                ep['Phi'] = p.get('Phi', 0)
                ep['y1'] = p.get('y1', 0)
                ep['x1'] = p.get('x1', 0)
                ep['x2'] = p.get('x2', 0)
                ep['y2'] = p.get('y2', 0)
                ep['x3'] = p.get('x3', 0)
                ep['x4'] = p.get('x4', 0)
                ep['Alph'] = p.get('Alph', 0)

            elif solid_type == 'twistedtubs':
                ep['twistedangle'] = p.get('twistedangle', 0)
                ep['endinnerrad'] = p.get('endinnerrad', 0)
                ep['endouterrad'] = p.get('endouterrad', 0)
                ep['zlen'] = p.get('zlen', 0) / 2.0
                ep['phi'] = p.get('phi', 2 * math.pi)

            elif solid_type in ['genericPolycone', 'genericPolyhedra']:
                ep['startphi'] = p.get('startphi', 0)
                ep['deltaphi'] = p.get('deltaphi', 2 * math.pi)
                ep['rzpoints'] = p.get('rzpoints', [])
                if solid_type == 'genericPolyhedra':
                    ep['numsides'] = p.get('numsides', 32)

            elif solid_type == 'xtru':
                # Evaluate all the nested dictionaries of expressions
                ep['twoDimVertices'] = []
                for v in p.get('twoDimVertices', []):
                    ep['twoDimVertices'].append({
                        'x': evaluator.evaluate(str(v.get('x', '0')))[1],
                        'y': evaluator.evaluate(str(v.get('y', '0')))[1]
                    })
                
                ep['sections'] = []
                for s in p.get('sections', []):
                    ep['sections'].append({
                        'zOrder': int(evaluator.evaluate(str(s.get('zOrder', '0')))[1]),
                        'zPosition': evaluator.evaluate(str(s.get('zPosition', '0')))[1],
                        'xOffset': evaluator.evaluate(str(s.get('xOffset', '0')))[1],
                        'yOffset': evaluator.evaluate(str(s.get('yOffset', '0')))[1],
                        'scalingFactor': evaluator.evaluate(str(s.get('scalingFactor', '1.0')))[1]
                    })
                # Sort sections by zOrder just in case
                ep['sections'].sort(key=lambda s: s['zOrder'])

            else:
                # For all other solids, just copy the evaluated params.
                # This is safe because their parameters are generally all required.
                solid._evaluated_parameters = p

        # --- Stage 4: Evaluate all placement transforms ---

        # Get all LVs and Assemblies to check for placements
        all_lvs = list(state.logical_volumes.values())
        all_asms = list(state.assemblies.values())

        # Iterate through LVs to evaluate their placements
        for lv in all_lvs:
            if lv.content_type == 'physvol':
                for pv in lv.content: # Use the new .content attribute
                    try:
                        pv.copy_number = int(evaluator.evaluate(str(pv.copy_number_expr))[1])
                    except Exception as e:
                        pv.copy_number = 0
                    
                    pv._evaluated_position = evaluate_transform_part(pv.position, {'x': 0, 'y': 0, 'z': 0}, rotation=False)
                    pv._evaluated_rotation = evaluate_transform_part(pv.rotation, {'x': 0, 'y': 0, 'z': 0}, rotation=True)
                    pv._evaluated_scale = evaluate_transform_part(pv.scale, {'x': 1, 'y': 1, 'z': 1}, rotation=False)
            
            elif lv.content_type in ['replica', 'division', 'parameterised']:
                # For procedural placements, we need to evaluate their parameters (width, offset, etc.)
                proc_obj = lv.content
                if proc_obj:

                    # Evaluate common procedural parameters if they exist
                    if hasattr(proc_obj, 'width'):
                        try:
                            proc_obj._evaluated_width = float(evaluator.evaluate(str(proc_obj.width))[1])
                        except Exception: proc_obj._evaluated_width = 0.0
                    if hasattr(proc_obj, 'offset'):
                        try:
                            proc_obj._evaluated_offset = float(evaluator.evaluate(str(proc_obj.offset))[1])
                        except Exception: proc_obj._evaluated_offset = 0.0
                    if hasattr(proc_obj, 'number'):
                        try:
                            proc_obj._evaluated_number = int(evaluator.evaluate(str(proc_obj.number))[1])
                        except Exception: proc_obj._evaluated_number = 0
                    
                    # Evaluate replica-specific transforms if they exist
                    if hasattr(proc_obj, 'start_position'):
                        proc_obj._evaluated_start_position = evaluate_transform_part(proc_obj.start_position, {'x': 0, 'y': 0, 'z': 0}, rotation=False)
                    if hasattr(proc_obj, 'start_rotation'):
                        proc_obj._evaluated_start_rotation = evaluate_transform_part(proc_obj.start_rotation, {'x': 0, 'y': 0, 'z': 0}, rotation=True)

                    # Add evaluation logic for parameterised volumes
                    if hasattr(proc_obj, 'ncopies'):
                        try:
                            proc_obj._evaluated_ncopies = int(evaluator.evaluate(str(proc_obj.ncopies))[1])
                        except Exception: proc_obj._evaluated_ncopies = 0

                    if hasattr(proc_obj, 'parameters'):
                        for param_set in proc_obj.parameters:
                            # Evaluate the transform for this instance
                            param_set._evaluated_position = evaluate_transform_part(param_set.position, {'x': 0, 'y': 0, 'z': 0}, rotation=False)
                            param_set._evaluated_rotation = evaluate_transform_part(param_set.rotation, {'x': 0, 'y': 0, 'z': 0}, rotation=True)
                            
                            # Evaluate each dimension expression for this instance
                            evaluated_dims = {}
                            for key, raw_expr in param_set.dimensions.items():
                                evaluated_dims[key] = evaluate_param_dimension_part(raw_expr, lv.name, key)
                            param_set._evaluated_dimensions = evaluated_dims


        # Iterate through Assemblies to evaluate their placements
        for asm in all_asms:
            for pv in asm.placements:
                try:
                    pv.copy_number = int(evaluator.evaluate(str(pv.copy_number_expr))[1])
                except Exception as e:
                    pv.copy_number = 0
                
                pv._evaluated_position = evaluate_transform_part(pv.position, {'x': 0, 'y': 0, 'z': 0})
                pv._evaluated_rotation = evaluate_transform_part(pv.rotation, {'x': 0, 'y': 0, 'z': 0})
                pv._evaluated_scale = evaluate_transform_part(pv.scale, {'x': 1, 'y': 1, 'z': 1})

        ## Stage 5 - Evaluate transforms inside boolean solid recipes ##
        for solid in state.solids.values():
            if solid.type == 'boolean':
                recipe = solid.raw_parameters.get('recipe', [])
                for item in recipe:
                    transform = item.get('transform', {})
                    if transform:
                         # Use the same helper to evaluate the nested transforms
                         transform['_evaluated_position'] = evaluate_transform_part(transform.get('position'), {'x':0, 'y':0, 'z':0})
                         transform['_evaluated_rotation'] = evaluate_transform_part(transform.get('rotation'), {'x':0, 'y':0, 'z':0})

        # --- Evaluate Source Positions ---
        for source in state.sources.values():
            source._evaluated_position = evaluate_transform_part(source.position, {'x': 0, 'y': 0, 'z': 0})
            source._evaluated_rotation = evaluate_transform_part(source.rotation, {'x': 0, 'y': 0, 'z': 0}, rotation=True)

        return True, None

    def load_gdml_from_string(self, gdml_string):
        """
        Orchestrates GDML parsing AND evaluation.
        """
        # Step 1: Parse the GDML into a raw state with expressions.
        self.current_geometry_state = self.gdml_parser.parse_gdml_string(gdml_string)
        
        # Step 2: Now that the full raw state is loaded, evaluate everything.
        success, error_msg = self.recalculate_geometry_state()
        if not success:
            print(f"Warning after parsing GDML: {error_msg}")
            # Even if it fails, we return the partially evaluated state for debugging.

        # --- Reset history on load ---
        self.history = []
        self.history_index = -1
        self._capture_history_state("Loaded project from GDML")
        
        return self.current_geometry_state

    def get_threejs_description(self):
        if self.current_geometry_state:
            return self.current_geometry_state.get_threejs_scene_description()
        return []

    def save_project_to_json_string(self):
        if self.current_geometry_state:
            data = self.current_geometry_state.to_dict()
            
            # Ensure chat history is JSON serializable (no raw Message objects)
            clean_history = []
            for msg in self.chat_history:
                if isinstance(msg, dict):
                    # Deep-sanitize the dict to catch nested non-serializable objects
                    def sanitize_deep(obj):
                        if isinstance(obj, dict):
                            return {k: sanitize_deep(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [sanitize_deep(i) for i in obj]
                        elif isinstance(obj, (str, int, float, bool, type(None))):
                            return obj
                        else:
                            return str(obj) # Force to string
                    
                    clean_history.append(sanitize_deep(msg))
                else:
                    # Convert Gemini Content/Part or Ollama Message objects to simple dicts
                    try:
                        clean_history.append({
                            "role": getattr(msg, 'role', 'assistant'),
                            "content": str(getattr(msg, 'content', ''))
                        })
                    except:
                        pass
            
            data['chat_history'] = clean_history
            return json.dumps(data, indent=2)
        return "{}"

    def load_project_from_json_string(self, json_string):
        data = json.loads(json_string)
        self.current_geometry_state = GeometryState.from_dict(data)
        self.chat_history = data.get('chat_history', [])
        
        success, error_msg = self.recalculate_geometry_state()
        if not success:
            print(f"Warning after loading JSON project: {error_msg}")

        # --- Reset history on load ---
        self.history = []
        self.history_index = -1
        self._capture_history_state("Loaded project from JSON")
        
        # Mark as changed so simulation will export fresh GDML
        self.is_changed = True

        return self.current_geometry_state

    def export_to_gdml_string(self):
        if self.current_geometry_state:
            writer = GDMLWriter(self.current_geometry_state)
            return writer.get_gdml_string()
        return "<?xml version='1.0' encoding='UTF-8'?>\n<gdml />"
    
    def get_full_project_state_dict(self, exclude_unchanged_tessellated=False):
        """
        Returns the entire current geometry state as a dictionary.
        Can optionally filter out heavy, unchanged tessellated solids.
        """
        if not self.current_geometry_state:
            return {}

        state_dict = self.current_geometry_state.to_dict()
        
        # For now, the only object tracking optimization involves large tessellated solids.
        if exclude_unchanged_tessellated:
            filtered_solids = {}
            changed_solids_set = self.changed_object_ids['solids'] or set()
            
            for name, solid_data in state_dict['solids'].items():
                is_tessellated = solid_data.get('type') == 'tessellated'
                # A tessellated solid is "static" if its facets have absolute vertices
                is_static = is_tessellated and \
                            len(solid_data['raw_parameters'].get('facets', [])) > 0 and \
                            'vertices' in solid_data['raw_parameters']['facets'][0]
                
                # Keep the solid if:
                # 1. It's not a static tessellated solid.
                # 2. It's one of the solids that was explicitly changed in this operation.
                if not is_static or name in changed_solids_set:
                    filtered_solids[name] = solid_data
            
            state_dict['solids'] = filtered_solids
        
        return state_dict

    def resolve_saved_run_manifest(self, sim_params=None, state=None):
        target_state = state if state is not None else self.current_geometry_state
        if target_state and hasattr(target_state, "scoring"):
            scoring_state = target_state.scoring
        else:
            scoring_state = ScoringState()
        return scoring_state.resolve_run_manifest(sim_params)

    def _validate_parameter_entry(self, name, entry, is_update=False):
        if not self.current_geometry_state:
            return False, "No active project state."

        if not name or not isinstance(name, str):
            return False, "Parameter name is required."

        if not isinstance(entry, dict):
            return False, "Parameter payload must be an object."

        target_type = entry.get('target_type')
        if target_type not in {'define', 'solid', 'source', 'sim_option'}:
            return False, "target_type must be one of: define, solid, source, sim_option."

        target_ref = entry.get('target_ref')
        if not isinstance(target_ref, dict):
            return False, "target_ref must be an object."

        bounds = entry.get('bounds')
        if not isinstance(bounds, dict):
            return False, "bounds must be an object with min/max."

        try:
            min_v = float(bounds.get('min'))
            max_v = float(bounds.get('max'))
        except (TypeError, ValueError):
            return False, "bounds.min and bounds.max must be numeric."

        if min_v >= max_v:
            return False, "bounds.min must be smaller than bounds.max."

        try:
            default_v = float(entry.get('default'))
        except (TypeError, ValueError):
            return False, "default must be numeric."

        if default_v < min_v or default_v > max_v:
            return False, "default must be inside [bounds.min, bounds.max]."

        # Target validation
        if target_type == 'define':
            define_name = target_ref.get('name')
            if not define_name or define_name not in self.current_geometry_state.defines:
                return False, f"Define target '{define_name}' not found."
        elif target_type == 'solid':
            solid_name = target_ref.get('name')
            param_name = target_ref.get('param')
            if not solid_name or solid_name not in self.current_geometry_state.solids:
                return False, f"Solid target '{solid_name}' not found."
            if not param_name:
                return False, "Solid parameter target_ref.param is required."
        elif target_type == 'source':
            source_name = target_ref.get('name')
            field_name = target_ref.get('field')
            if not source_name or source_name not in self.current_geometry_state.sources:
                return False, f"Source target '{source_name}' not found."
            if not field_name:
                return False, "Source target_ref.field is required."
        elif target_type == 'sim_option':
            option_key = target_ref.get('key')
            if not option_key:
                return False, "sim_option target_ref.key is required."

        return True, None

    def list_parameter_registry(self):
        if not self.current_geometry_state:
            return {}
        return dict(self.current_geometry_state.parameter_registry or {})

    def upsert_parameter_registry_entry(self, name, entry):
        if not self.current_geometry_state:
            return None, "No active project state."

        ok, err = self._validate_parameter_entry(name, entry)
        if not ok:
            return None, err

        registry = self.current_geometry_state.parameter_registry
        if name in registry and entry.get('name') and entry.get('name') != name:
            return None, "Payload name must match parameter key for updates."

        normalized = {
            'name': name,
            'target_type': entry.get('target_type'),
            'target_ref': entry.get('target_ref'),
            'bounds': {
                'min': float(entry['bounds']['min']),
                'max': float(entry['bounds']['max']),
            },
            'default': float(entry.get('default')),
            'units': entry.get('units', ''),
            'enabled': bool(entry.get('enabled', True)),
            'constraint_group': entry.get('constraint_group'),
        }

        registry[name] = normalized
        self._capture_history_state(f"Updated parameter registry entry '{name}'")
        return normalized, None

    def delete_parameter_registry_entry(self, name):
        if not self.current_geometry_state:
            return False, "No active project state."

        registry = self.current_geometry_state.parameter_registry
        if name not in registry:
            return False, f"Parameter '{name}' not found."

        del registry[name]
        self._capture_history_state(f"Deleted parameter registry entry '{name}'")
        return True, None

    def _validate_param_study(self, name, config):
        if not self.current_geometry_state:
            return False, "No active project state."
        if not name or not isinstance(name, str):
            return False, "Study name is required."
        if not isinstance(config, dict):
            return False, "Study config must be an object."

        mode = config.get('mode', 'grid')
        if mode not in {'grid', 'random'}:
            return False, "Study mode must be 'grid' or 'random'."

        params = config.get('parameters', [])
        if not isinstance(params, list) or not params:
            return False, "Study must include a non-empty parameter list."

        registry = self.current_geometry_state.parameter_registry or {}
        for p in params:
            if p not in registry:
                return False, f"Parameter '{p}' not found in registry."

        if mode == 'grid':
            grid_cfg = config.get('grid', {}) or {}
            steps = int(grid_cfg.get('steps', 3))
            if steps < 2:
                return False, "Grid studies require at least 2 steps."
            if steps > self.MAX_PARAM_STUDY_RUNS:
                return False, f"Grid steps too large. Max allowed is {self.MAX_PARAM_STUDY_RUNS}."
        else:
            rnd_cfg = config.get('random', {}) or {}
            samples = int(rnd_cfg.get('samples', 10))
            if samples < 1:
                return False, "Random studies require at least 1 sample."
            if samples > self.MAX_PARAM_STUDY_RUNS:
                return False, f"Random samples too large. Max allowed is {self.MAX_PARAM_STUDY_RUNS}."

        objectives = config.get('objectives', []) or []
        if not isinstance(objectives, list):
            return False, "objectives must be a list."
        allowed_metrics = {
            'success_flag',
            'solids_count',
            'logical_volumes_count',
            'placements_count',
            'sources_count',
            'parameter_value',
            'sim_metric',
            'formula',
            'silicon_slab_edep_fraction',
            'silicon_slab_cost_norm',
            'silicon_slab_tradeoff',
        }
        for idx, obj in enumerate(objectives):
            if not isinstance(obj, dict):
                return False, f"Objective at index {idx} must be an object."
            metric = obj.get('metric')
            if metric not in allowed_metrics:
                return False, f"Objective metric '{metric}' is not supported."
            direction = obj.get('direction', 'maximize')
            if direction not in {'maximize', 'minimize'}:
                return False, f"Objective direction '{direction}' is invalid."
            if metric == 'parameter_value' and not obj.get('parameter'):
                return False, "Objective metric 'parameter_value' requires field 'parameter'."

            if metric == 'sim_metric' and not obj.get('key'):
                return False, "Objective metric 'sim_metric' requires field 'key'."

            if metric == 'formula' and not (obj.get('expression') or obj.get('expr')):
                return False, "Objective metric 'formula' requires field 'expression'."

            if metric in {'silicon_slab_edep_fraction', 'silicon_slab_cost_norm', 'silicon_slab_tradeoff'}:
                thickness_param = obj.get('thickness_parameter')
                if not thickness_param:
                    return False, f"Objective metric '{metric}' requires field 'thickness_parameter'."
                if thickness_param not in params:
                    return False, f"Objective metric '{metric}' thickness_parameter '{thickness_param}' must be in study parameters."

        return True, None

    def list_param_studies(self):
        if not self.current_geometry_state:
            return {}
        return dict(self.current_geometry_state.param_studies or {})

    def upsert_param_study(self, name, config):
        ok, err = self._validate_param_study(name, config)
        if not ok:
            return None, err

        mode = config.get('mode', 'grid')
        normalized = {
            'name': name,
            'mode': mode,
            'parameters': list(config.get('parameters', [])),
            'simulation_source_ids': [
                str(source_id).strip()
                for source_id in (config.get('simulation_source_ids') or [])
                if str(source_id).strip()
            ],
            'grid': config.get('grid', {}) or {},
            'random': config.get('random', {}) or {},
            'objectives': config.get('objectives', []) or [],
        }

        if mode == 'grid':
            normalized['grid'].setdefault('steps', 3)
            normalized['grid'].setdefault('per_parameter_steps', {})
        else:
            normalized['random'].setdefault('samples', 10)
            normalized['random'].setdefault('seed', 42)

        self.current_geometry_state.param_studies[name] = normalized
        self._capture_history_state(f"Updated param study '{name}'")
        return normalized, None

    def delete_param_study(self, name):
        if not self.current_geometry_state:
            return False, "No active project state."
        studies = self.current_geometry_state.param_studies
        if name not in studies:
            return False, f"Study '{name}' not found."
        del studies[name]
        self._capture_history_state(f"Deleted param study '{name}'")
        return True, None

    def _apply_param_value(self, param_entry, value, sim_options):
        target_type = param_entry.get('target_type')
        target_ref = param_entry.get('target_ref', {})
        value_str = str(value)

        if target_type == 'define':
            dname = target_ref.get('name')
            define = self.current_geometry_state.defines.get(dname)
            if define is None:
                return False, f"Define target '{dname}' not found."
            define.raw_expression = value_str
            return True, None

        if target_type == 'solid':
            sname = target_ref.get('name')
            pname = target_ref.get('param')
            solid = self.current_geometry_state.solids.get(sname)
            if solid is None:
                return False, f"Solid target '{sname}' not found."
            if not pname:
                return False, "Solid target param is missing."
            solid.raw_parameters[pname] = value_str
            return True, None

        if target_type == 'source':
            src_name = target_ref.get('name')
            field = target_ref.get('field')
            source = self.current_geometry_state.sources.get(src_name)
            if source is None:
                return False, f"Source target '{src_name}' not found."
            if not field:
                return False, "Source field target is missing."

            if field.startswith('position.'):
                axis = field.split('.', 1)[1]
                source.position[axis] = value_str
            elif field.startswith('rotation.'):
                axis = field.split('.', 1)[1]
                source.rotation[axis] = value_str
            elif field == 'activity':
                source.activity = float(value)
            else:
                setattr(source, field, value)
            return True, None

        if target_type == 'sim_option':
            key = target_ref.get('key')
            if not key:
                return False, "sim_option key is missing."
            sim_options[key] = value
            return True, None

        return False, f"Unsupported target_type '{target_type}'."

    def _compute_run_metrics(self):
        """Compute lightweight per-run metrics for study objective evaluation."""
        state = self.current_geometry_state
        placement_count = 0
        for lv in state.logical_volumes.values():
            if lv.content_type == 'physvol' and isinstance(lv.content, list):
                placement_count += len(lv.content)
        for asm in state.assemblies.values():
            placement_count += len(getattr(asm, 'placements', []) or [])

        return {
            'solids_count': len(state.solids),
            'logical_volumes_count': len(state.logical_volumes),
            'sources_count': len(state.sources),
            'placements_count': placement_count,
        }

    def _compute_silicon_slab_terms(self, objective_cfg, run_record):
        values = run_record.get('values', {}) or {}
        thickness_param = objective_cfg.get('thickness_parameter')
        if not thickness_param:
            return None

        try:
            thickness_mm = float(values.get(thickness_param))
        except (TypeError, ValueError):
            return None

        thickness_mm = max(0.0, thickness_mm)

        attenuation_length_mm = float(objective_cfg.get('attenuation_length_mm', 1.5))
        attenuation_length_mm = max(1e-9, attenuation_length_mm)

        reference_thickness_mm = float(objective_cfg.get('reference_thickness_mm', 3.0))
        reference_thickness_mm = max(1e-9, reference_thickness_mm)

        w_edep = float(objective_cfg.get('w_edep', 0.8))
        w_cost = float(objective_cfg.get('w_cost', 0.2))

        edep_fraction = 1.0 - float(np.exp(-thickness_mm / attenuation_length_mm))
        edep_fraction = max(0.0, min(1.0, edep_fraction))

        cost_norm = thickness_mm / reference_thickness_mm
        score = (w_edep * edep_fraction) - (w_cost * cost_norm)

        return {
            'thickness_mm': thickness_mm,
            'edep_fraction': edep_fraction,
            'cost_norm': float(cost_norm),
            'score': float(score),
            'w_edep': w_edep,
            'w_cost': w_cost,
            'attenuation_length_mm': attenuation_length_mm,
            'reference_thickness_mm': reference_thickness_mm,
        }

    def _evaluate_study_objectives(self, objectives, run_record):
        """Evaluate configured objectives from run-local metrics.

        Supported objective fields:
          - name (optional; defaults to metric)
          - metric: success_flag|solids_count|logical_volumes_count|placements_count|sources_count|parameter_value|
                    sim_metric|formula|silicon_slab_edep_fraction|silicon_slab_cost_norm|silicon_slab_tradeoff
          - direction: maximize|minimize (metadata only for now)
          - parameter: required when metric=parameter_value
          - key: required when metric=sim_metric
          - expression: required when metric=formula
          - thickness_parameter: required for silicon_slab_* metrics
        """
        if not objectives:
            return {}

        out = {}
        metrics = run_record.get('metrics', {}) or {}
        sim_metrics = run_record.get('sim_metrics', {}) or {}
        success = 1.0 if run_record.get('success') else 0.0

        for obj in objectives:
            if not isinstance(obj, dict):
                continue
            metric = obj.get('metric')
            if not metric:
                continue
            name = obj.get('name', metric)

            if metric == 'success_flag':
                out[name] = success
            elif metric in {'solids_count', 'logical_volumes_count', 'placements_count', 'sources_count'}:
                out[name] = float(metrics.get(metric, 0.0))
            elif metric == 'parameter_value':
                param_name = obj.get('parameter')
                if not param_name:
                    continue
                try:
                    out[name] = float(run_record.get('values', {}).get(param_name))
                except (TypeError, ValueError):
                    pass
            elif metric == 'sim_metric':
                key = obj.get('key')
                if not key:
                    continue
                try:
                    out[name] = float(sim_metrics.get(key))
                except (TypeError, ValueError):
                    pass
            elif metric == 'formula':
                expr = obj.get('expression') or obj.get('expr')
                if not expr:
                    continue
                env = {}
                env.update(metrics)
                env.update(run_record.get('values', {}) or {})
                env.update(sim_metrics)
                env.update(out)
                try:
                    out[name] = float(evaluate_objective_formula(expr, env))
                except Exception:
                    continue
            elif metric in {'silicon_slab_edep_fraction', 'silicon_slab_cost_norm', 'silicon_slab_tradeoff'}:
                terms = self._compute_silicon_slab_terms(obj, run_record)
                if not terms:
                    continue
                if metric == 'silicon_slab_edep_fraction':
                    out[name] = float(terms['edep_fraction'])
                elif metric == 'silicon_slab_cost_norm':
                    out[name] = float(terms['cost_norm'])
                else:
                    out[name] = float(terms['score'])

        return out

    def _generate_param_study_samples(self, study):
        registry = self.current_geometry_state.parameter_registry
        param_names = study.get('parameters', [])
        mode = study.get('mode', 'grid')

        if mode == 'grid':
            grid_cfg = study.get('grid', {}) or {}
            default_steps = int(grid_cfg.get('steps', 3))
            per_param_steps = grid_cfg.get('per_parameter_steps', {}) or {}

            value_arrays = []
            for p in param_names:
                p_entry = registry[p]
                mn = float(p_entry['bounds']['min'])
                mx = float(p_entry['bounds']['max'])
                steps = int(per_param_steps.get(p, default_steps))
                steps = max(2, steps)
                value_arrays.append(np.linspace(mn, mx, steps).tolist())

            samples = []
            for combo in itertools.product(*value_arrays):
                sample = {param_names[i]: float(combo[i]) for i in range(len(param_names))}
                samples.append(sample)
            return samples

        rnd_cfg = study.get('random', {}) or {}
        n_samples = max(1, int(rnd_cfg.get('samples', 10)))
        seed = int(rnd_cfg.get('seed', 42))
        rng = random.Random(seed)

        samples = []
        for _ in range(n_samples):
            sample = {}
            for p in param_names:
                p_entry = registry[p]
                mn = float(p_entry['bounds']['min'])
                mx = float(p_entry['bounds']['max'])
                sample[p] = rng.uniform(mn, mx)
            samples.append(sample)
        return samples

    def run_param_study(self, name, max_runs=None):
        if not self.current_geometry_state:
            return None, "No active project state."

        studies = self.current_geometry_state.param_studies or {}
        if name not in studies:
            return None, f"Study '{name}' not found."

        study = studies[name]
        samples = self._generate_param_study_samples(study)
        requested_limit = self.MAX_PARAM_STUDY_RUNS
        if max_runs is not None:
            requested_limit = min(requested_limit, max(0, int(max_runs)))
        samples = samples[:requested_limit]

        original_state = GeometryState.from_dict(self.current_geometry_state.to_dict())
        runs = []
        success_count = 0
        stop_reason = 'completed'

        self.update_managed_run_progress(
            total_evaluations=len(samples),
            evaluations_completed=0,
            success_count=0,
            failure_count=0,
            phase='running',
            message=f"Parameter sweep '{name}' started.",
        )

        try:
            for i, sample in enumerate(samples):
                abort_reason = self._should_abort_managed_run()
                if abort_reason:
                    stop_reason = abort_reason
                    break
                self.current_geometry_state = GeometryState.from_dict(original_state.to_dict())

                self.update_managed_run_progress(
                    current_run_index=i,
                    current_values=sample,
                    evaluations_completed=len(runs),
                    success_count=success_count,
                    failure_count=len(runs) - success_count,
                    phase='evaluating',
                    message=f"Evaluating candidate {i + 1}/{len(samples)}",
                )

                sim_options = {}
                apply_error = None
                for param_name, value in sample.items():
                    param_entry = self.current_geometry_state.parameter_registry.get(param_name)
                    if not param_entry:
                        apply_error = f"Parameter '{param_name}' missing in registry during run."
                        break
                    ok, err = self._apply_param_value(param_entry, value, sim_options)
                    if not ok:
                        apply_error = err
                        break

                if apply_error:
                    run_record = {
                        'run_index': i,
                        'values': sample,
                        'sim_options': sim_options,
                        'success': False,
                        'error': apply_error,
                        'metrics': {},
                    }
                    run_record['objectives'] = self._evaluate_study_objectives(study.get('objectives', []), run_record)
                    runs.append(run_record)
                    self.update_managed_run_progress(
                        evaluations_completed=len(runs),
                        success_count=success_count,
                        failure_count=len(runs) - success_count,
                        phase='evaluating',
                        message=f"Candidate {i + 1}/{len(samples)} failed: {apply_error}",
                    )
                    continue

                ok, err = self.recalculate_geometry_state()
                if ok:
                    success_count += 1

                run_record = {
                    'run_index': i,
                    'values': sample,
                    'sim_options': sim_options,
                    'success': bool(ok),
                    'error': err,
                    'metrics': self._compute_run_metrics() if ok else {},
                }
                run_record['objectives'] = self._evaluate_study_objectives(study.get('objectives', []), run_record)

                runs.append(run_record)
                self.update_managed_run_progress(
                    evaluations_completed=len(runs),
                    success_count=success_count,
                    failure_count=len(runs) - success_count,
                    phase='evaluating',
                    message=f"Candidate {i + 1}/{len(samples)} {'ok' if run_record.get('success') else 'failed'}",
                )
        finally:
            self.current_geometry_state = original_state
            self.recalculate_geometry_state()

        self.update_managed_run_progress(
            evaluations_completed=len(runs),
            success_count=success_count,
            failure_count=len(runs) - success_count,
            phase=stop_reason,
            current_values={},
            message=f"Parameter sweep finished with status '{stop_reason}'.",
        )

        return {
            'study_name': name,
            'mode': study.get('mode'),
            'requested_runs': len(samples),
            'evaluations_used': len(runs),
            'successful_runs': success_count,
            'failed_runs': len(runs) - success_count,
            'stop_reason': stop_reason,
            'runs': runs,
        }, None

    def apply_study_candidate_values(self, study_name, values):
        if not self.current_geometry_state:
            return None, "No active project state."

        studies = self.current_geometry_state.param_studies or {}
        if study_name not in studies:
            return None, f"Study '{study_name}' not found."

        if not isinstance(values, dict) or not values:
            return None, "values must be a non-empty object/dict."

        study = studies[study_name]
        study_params = list(study.get('parameters', []) or [])

        sim_options = {}
        applied_values = {}
        for param_name in study_params:
            if param_name not in values:
                continue
            param_entry = self.current_geometry_state.parameter_registry.get(param_name)
            if not param_entry:
                return None, f"Parameter '{param_name}' not found in registry."

            raw_v = values.get(param_name)
            try:
                v = float(raw_v)
            except (TypeError, ValueError):
                return None, f"Parameter '{param_name}' value must be numeric."

            ok, err = self._apply_param_value(param_entry, v, sim_options)
            if not ok:
                return None, err
            applied_values[param_name] = v

        if not applied_values:
            return None, "No matching study parameters found in values payload."

        ok, err = self.recalculate_geometry_state()
        if not ok:
            return None, err

        self._capture_history_state(f"Applied candidate values for study '{study_name}'")

        return {
            'study_name': study_name,
            'applied_values': applied_values,
            'sim_options': sim_options,
        }, None

    def _evaluate_param_sample(self, study, sample, run_index=0, evaluator=None):
        sim_options = {}
        apply_error = None
        for param_name, value in sample.items():
            param_entry = self.current_geometry_state.parameter_registry.get(param_name)
            if not param_entry:
                apply_error = f"Parameter '{param_name}' missing in registry during run."
                break
            ok, err = self._apply_param_value(param_entry, value, sim_options)
            if not ok:
                apply_error = err
                break

        if apply_error:
            run_record = {
                'run_index': run_index,
                'values': sample,
                'sim_options': sim_options,
                'success': False,
                'error': apply_error,
                'metrics': {},
                'sim_metrics': {},
            }
            run_record['objectives'] = self._evaluate_study_objectives(study.get('objectives', []), run_record)
            return run_record

        ok, err = self.recalculate_geometry_state()
        run_record = {
            'run_index': run_index,
            'values': sample,
            'sim_options': sim_options,
            'success': bool(ok),
            'error': err,
            'metrics': self._compute_run_metrics() if ok else {},
            'sim_metrics': {},
        }

        if run_record['success'] and callable(evaluator):
            try:
                sim_eval = evaluator(run_record=run_record, project_manager=self, study=study) or {}
                sim_success = bool(sim_eval.get('success', True))
                run_record['sim_metrics'] = dict(sim_eval.get('sim_metrics', {}) or {})
                if sim_eval.get('simulation') is not None:
                    run_record['simulation'] = sim_eval.get('simulation')
                if not sim_success:
                    run_record['success'] = False
                    run_record['error'] = sim_eval.get('error', 'Simulation evaluator failed.')
            except Exception as e:
                run_record['success'] = False
                run_record['error'] = f"Simulation evaluator exception: {e}"

        run_record['objectives'] = self._evaluate_study_objectives(study.get('objectives', []), run_record)
        return run_record

    def _score_run_for_objective(self, run_record, objective_name, direction='maximize'):
        val = run_record.get('objectives', {}).get(objective_name)
        if val is None:
            return -float('inf')
        try:
            x = float(val)
        except (TypeError, ValueError):
            return -float('inf')
        return x if direction == 'maximize' else -x

    def _get_optimizer_bounds(self, param_names, registry):
        mins = np.array([float(registry[p]['bounds']['min']) for p in param_names], dtype=float)
        maxs = np.array([float(registry[p]['bounds']['max']) for p in param_names], dtype=float)
        return mins, maxs

    def _vector_to_sample(self, param_names, vec):
        return {param_names[i]: float(vec[i]) for i in range(len(param_names))}

    def _evaluate_candidate_vector(self, study, param_names, vec, mins, maxs, run_index, objective_name, direction, penalty_weight=0.0, generation=None, evaluator=None):
        clipped = np.clip(vec, mins, maxs)
        violation = vec - clipped
        boundary_penalty = penalty_weight * float(np.linalg.norm(violation))

        sample = self._vector_to_sample(param_names, clipped)
        run_record = self._evaluate_param_sample(study, sample, run_index=run_index, evaluator=evaluator)

        raw_score = self._score_run_for_objective(run_record, objective_name, direction=direction)
        score = raw_score - boundary_penalty

        run_record['optimizer_raw_score'] = raw_score
        run_record['optimizer_penalty'] = boundary_penalty
        run_record['optimizer_score'] = score
        if generation is not None:
            run_record['generation'] = generation

        return run_record, clipped

    def _run_random_search_optimizer(self, study, param_names, registry, objective_name, direction, budget, seed, evaluator=None):
        rng = random.Random(seed)
        mins, maxs = self._get_optimizer_bounds(param_names, registry)

        candidates = []
        best = None
        best_score = -float('inf')
        stop_reason = 'budget_exhausted'

        self.update_managed_run_progress(
            total_evaluations=budget,
            evaluations_completed=0,
            success_count=0,
            failure_count=0,
            phase='running',
            message=f"Optimizer random_search started (budget={budget}).",
        )

        for i in range(budget):
            abort_reason = self._should_abort_managed_run()
            if abort_reason:
                stop_reason = abort_reason
                break
            sample = {}
            for p in param_names:
                entry = registry[p]
                mn = float(entry['bounds']['min'])
                mx = float(entry['bounds']['max'])
                sample[p] = rng.uniform(mn, mx)

            self.update_managed_run_progress(
                current_run_index=i,
                current_values=sample,
                evaluations_completed=len(candidates),
                success_count=sum(1 for c in candidates if c.get('success')),
                failure_count=sum(1 for c in candidates if not c.get('success')),
                phase='evaluating',
                message=f"Evaluating candidate {i + 1}/{budget}",
            )

            run_record = self._evaluate_param_sample(study, sample, run_index=i, evaluator=evaluator)
            score = self._score_run_for_objective(run_record, objective_name, direction=direction)
            run_record['optimizer_score'] = score
            run_record['optimizer_raw_score'] = score
            run_record['optimizer_penalty'] = 0.0
            candidates.append(run_record)

            if score > best_score:
                best_score = score
                best = run_record

            self.update_managed_run_progress(
                evaluations_completed=len(candidates),
                success_count=sum(1 for c in candidates if c.get('success')),
                failure_count=sum(1 for c in candidates if not c.get('success')),
                phase='evaluating',
                message=f"Completed candidate {i + 1}/{budget}",
            )

        self.update_managed_run_progress(
            evaluations_completed=len(candidates),
            success_count=sum(1 for c in candidates if c.get('success')),
            failure_count=sum(1 for c in candidates if not c.get('success')),
            phase=stop_reason,
            current_values={},
            message=f"Optimizer random_search finished with status '{stop_reason}'.",
        )

        return {
            'candidates': candidates,
            'best': best,
            'stop_reason': stop_reason,
            'generation_stats': [],
            'step_size_history': [],
            'evaluations_used': len(candidates),
        }

    def _run_cmaes_optimizer(self, study, param_names, registry, objective_name, direction, budget, seed, cmaes_config=None, evaluator=None):
        cfg = cmaes_config or {}
        rng = np.random.default_rng(seed)

        mins, maxs = self._get_optimizer_bounds(param_names, registry)
        n = len(param_names)
        if n <= 0:
            return {
                'candidates': [],
                'best': None,
                'stop_reason': 'no_parameters',
                'generation_stats': [],
                'step_size_history': [],
                'evaluations_used': 0,
            }

        pop_size_default = max(4, 4 + int(3 * np.log(max(2, n))))
        lambda_pop = int(cfg.get('population_size', pop_size_default))
        lambda_pop = max(4, min(lambda_pop, budget))
        mu = max(1, lambda_pop // 2)

        raw_weights = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
        weights = raw_weights / np.sum(raw_weights)
        mueff = (np.sum(weights) ** 2) / np.sum(weights ** 2)

        ranges = np.maximum(maxs - mins, 1e-12)
        mean = np.array([float(registry[p].get('default', (mins[i] + maxs[i]) * 0.5)) for i, p in enumerate(param_names)], dtype=float)
        mean = np.clip(mean, mins, maxs)

        sigma_rel = float(cfg.get('sigma_rel', 0.3))
        sigma = float(cfg.get('sigma', sigma_rel * float(np.mean(ranges))))
        sigma = max(sigma, 1e-12)

        cc = (4 + mueff / n) / (n + 4 + 2 * mueff / n)
        cs = (mueff + 2) / (n + mueff + 5)
        c1 = 2 / ((n + 1.3) ** 2 + mueff)
        cmu = min(1 - c1, 2 * (mueff - 2 + 1 / mueff) / ((n + 2) ** 2 + mueff))
        damps = 1 + 2 * max(0, np.sqrt((mueff - 1) / (n + 1)) - 1) + cs
        chi_n = np.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * (n ** 2)))

        C = np.eye(n)
        B = np.eye(n)
        D = np.ones(n)
        invsqrtC = np.eye(n)
        pc = np.zeros(n)
        ps = np.zeros(n)

        penalty_weight = float(cfg.get('boundary_penalty_weight', 1.0))
        stagnation_generations = max(1, int(cfg.get('stagnation_generations', 12)))
        min_improvement = float(cfg.get('min_improvement', 1e-9))
        sigma_min = float(cfg.get('sigma_min', 1e-12))

        candidates = []
        best = None
        best_score = -float('inf')
        no_improve_gens = 0
        generation = 0
        eval_count = 0
        generation_stats = []
        step_size_history = []
        stop_reason = 'budget_exhausted'

        self.update_managed_run_progress(
            total_evaluations=budget,
            evaluations_completed=0,
            success_count=0,
            failure_count=0,
            phase='running',
            message=f"Optimizer cmaes started (budget={budget}).",
        )

        while eval_count < budget:
            abort_reason = self._should_abort_managed_run()
            if abort_reason:
                stop_reason = abort_reason
                break

            pop = []
            for k in range(lambda_pop):
                if eval_count >= budget:
                    break

                abort_reason = self._should_abort_managed_run()
                if abort_reason:
                    stop_reason = abort_reason
                    break
                z = rng.standard_normal(n)
                y = B @ (D * z)
                x = mean + sigma * y
                sample_preview = self._vector_to_sample(param_names, np.clip(x, mins, maxs))

                self.update_managed_run_progress(
                    current_run_index=eval_count,
                    current_values=sample_preview,
                    evaluations_completed=len(candidates),
                    success_count=sum(1 for c in candidates if c.get('success')),
                    failure_count=sum(1 for c in candidates if not c.get('success')),
                    phase='evaluating',
                    message=f"Evaluating candidate {eval_count + 1}/{budget} (generation {generation})",
                )

                run_record, clipped = self._evaluate_candidate_vector(
                    study=study,
                    param_names=param_names,
                    vec=x,
                    mins=mins,
                    maxs=maxs,
                    run_index=eval_count,
                    objective_name=objective_name,
                    direction=direction,
                    penalty_weight=penalty_weight,
                    generation=generation,
                    evaluator=evaluator,
                )
                pop.append((run_record, clipped))
                candidates.append(run_record)
                eval_count += 1

                if run_record['optimizer_score'] > best_score:
                    best_score = run_record['optimizer_score']
                    best = run_record

                self.update_managed_run_progress(
                    evaluations_completed=len(candidates),
                    success_count=sum(1 for c in candidates if c.get('success')),
                    failure_count=sum(1 for c in candidates if not c.get('success')),
                    phase='evaluating',
                    message=f"Completed candidate {eval_count}/{budget}",
                )

            if stop_reason not in {'budget_exhausted', 'empty_population', 'sigma_min_reached', 'stagnation'}:
                break

            if not pop:
                stop_reason = 'empty_population'
                break

            pop.sort(key=lambda t: t[0]['optimizer_score'], reverse=True)
            selected = pop[:mu]

            old_mean = mean.copy()
            y_list = [(vec - old_mean) / sigma for _, vec in selected]
            y_w = np.sum(np.array([weights[i] * y_list[i] for i in range(len(y_list))]), axis=0)
            mean = old_mean + sigma * y_w
            mean = np.clip(mean, mins, maxs)

            ps = (1 - cs) * ps + np.sqrt(cs * (2 - cs) * mueff) * (invsqrtC @ y_w)
            norm_ps = np.linalg.norm(ps)
            hsig = 1.0 if (norm_ps / np.sqrt(1 - (1 - cs) ** (2 * (generation + 1))) / chi_n) < (1.4 + 2 / (n + 1)) else 0.0
            pc = (1 - cc) * pc + hsig * np.sqrt(cc * (2 - cc) * mueff) * y_w

            delta_hsig = (1 - hsig) * cc * (2 - cc)
            C = (1 - c1 - cmu + c1 * delta_hsig) * C + c1 * np.outer(pc, pc)
            for i in range(len(y_list)):
                C += cmu * weights[i] * np.outer(y_list[i], y_list[i])

            C = (C + C.T) * 0.5
            eigvals, eigvecs = np.linalg.eigh(C)
            eigvals = np.maximum(eigvals, 1e-20)
            D = np.sqrt(eigvals)
            B = eigvecs
            invsqrtC = B @ np.diag(1.0 / D) @ B.T

            sigma *= np.exp((cs / damps) * ((norm_ps / chi_n) - 1))
            sigma = max(sigma, sigma_min)

            step_size_history.append(float(sigma))

            gen_best = pop[0][0]
            generation_stats.append({
                'generation': generation,
                'evaluations_used': eval_count,
                'population_size': len(pop),
                'sigma': float(sigma),
                'generation_best_score': float(gen_best.get('optimizer_score', -float('inf'))),
                'generation_best_objective': gen_best.get('objectives', {}).get(objective_name),
            })

            if generation_stats and len(generation_stats) >= 2:
                prev_best = generation_stats[-2]['generation_best_score']
                curr_best = generation_stats[-1]['generation_best_score']
                if (curr_best - prev_best) > min_improvement:
                    no_improve_gens = 0
                else:
                    no_improve_gens += 1

            if sigma <= sigma_min:
                stop_reason = 'sigma_min_reached'
                break
            if no_improve_gens >= stagnation_generations:
                stop_reason = 'stagnation'
                break

            generation += 1

        self.update_managed_run_progress(
            evaluations_completed=len(candidates),
            success_count=sum(1 for c in candidates if c.get('success')),
            failure_count=sum(1 for c in candidates if not c.get('success')),
            phase=stop_reason,
            current_values={},
            message=f"Optimizer cmaes finished with status '{stop_reason}'.",
        )

        return {
            'candidates': candidates,
            'best': best,
            'stop_reason': stop_reason,
            'generation_stats': generation_stats,
            'step_size_history': step_size_history,
            'evaluations_used': len(candidates),
            'cmaes': {
                'population_size': lambda_pop,
                'mu': mu,
                'stagnation_generations': stagnation_generations,
                'min_improvement': min_improvement,
                'sigma_min': sigma_min,
                'boundary_penalty_weight': penalty_weight,
            },
        }

    def _rbf_kernel(self, x1, x2, length_scale):
        ls2 = max(float(length_scale) ** 2, 1e-12)
        d2 = np.sum((x1[:, None, :] - x2[None, :, :]) ** 2, axis=2)
        return np.exp(-0.5 * d2 / ls2)

    def _default_gp_length_scale(self, x):
        if x.shape[0] <= 1:
            return 1.0
        d2 = np.sum((x[:, None, :] - x[None, :, :]) ** 2, axis=2)
        d = np.sqrt(np.maximum(d2, 0.0))
        upper = d[np.triu_indices_from(d, k=1)]
        upper = upper[np.isfinite(upper)]
        upper = upper[upper > 0]
        if upper.size == 0:
            return 1.0
        return float(np.median(upper))

    def _fit_gp_surrogate(self, x_train, y_train, noise=1e-6, length_scale=None):
        if x_train.shape[0] < 2:
            return None

        if length_scale is None:
            length_scale = self._default_gp_length_scale(x_train)

        K = self._rbf_kernel(x_train, x_train, length_scale)
        K = K + float(noise) * np.eye(x_train.shape[0], dtype=float)

        try:
            alpha = np.linalg.solve(K, y_train)
        except np.linalg.LinAlgError:
            alpha = np.linalg.lstsq(K, y_train, rcond=None)[0]

        try:
            K_inv = np.linalg.inv(K)
        except np.linalg.LinAlgError:
            K_inv = np.linalg.pinv(K)

        return {
            'x_train': x_train,
            'y_train': y_train,
            'alpha': alpha,
            'K_inv': K_inv,
            'length_scale': float(length_scale),
            'noise': float(noise),
        }

    def _gp_predict_with_uncertainty(self, model, x_query):
        if not model:
            return np.zeros((x_query.shape[0],), dtype=float), np.ones((x_query.shape[0],), dtype=float)

        x_train = model['x_train']
        alpha = model['alpha']
        K_inv = model['K_inv']
        length_scale = model['length_scale']

        k_q = self._rbf_kernel(x_query, x_train, length_scale)
        mean = k_q @ alpha

        # RBF prior variance at each point is 1.0
        quad = np.sum((k_q @ K_inv) * k_q, axis=1)
        var = np.maximum(1e-12, 1.0 - quad)
        std = np.sqrt(var)
        return mean, std

    def _sample_random_candidate(self, param_names, registry, rng):
        sample = {}
        for p in param_names:
            entry = registry[p]
            mn = float(entry['bounds']['min'])
            mx = float(entry['bounds']['max'])
            sample[p] = rng.uniform(mn, mx)
        return sample

    def run_surrogate_param_optimizer(
        self,
        study_name,
        budget=40,
        seed=42,
        objective_name=None,
        direction=None,
        warmup_runs=10,
        candidate_pool_size=256,
        exploration_beta=1.0,
        gp_noise=1e-6,
        evaluator=None,
    ):
        if not self.current_geometry_state:
            return None, "No active project state."

        studies = self.current_geometry_state.param_studies or {}
        if study_name not in studies:
            return None, f"Study '{study_name}' not found."

        study = studies[study_name]
        param_names = study.get('parameters', [])
        if not param_names:
            return None, "Study has no parameters."

        registry = self.current_geometry_state.parameter_registry
        for p in param_names:
            if p not in registry:
                return None, f"Parameter '{p}' missing in registry."

        objectives = study.get('objectives', []) or []
        if objective_name is None:
            objective_name = objectives[0].get('name', objectives[0].get('metric')) if objectives else 'success_flag'

        if direction is None:
            direction = 'maximize'
            for o in objectives:
                nm = o.get('name', o.get('metric'))
                if nm == objective_name:
                    direction = o.get('direction', 'maximize')
                    break

        budget = max(1, min(int(budget), self.MAX_OPTIMIZER_BUDGET))
        warmup_runs = max(1, int(warmup_runs))
        candidate_pool_size = max(8, int(candidate_pool_size))
        exploration_beta = float(exploration_beta)
        gp_noise = float(gp_noise)

        original_state = GeometryState.from_dict(self.current_geometry_state.to_dict())
        rng = random.Random(int(seed))
        np_rng = np.random.default_rng(int(seed))

        mins, maxs = self._get_optimizer_bounds(param_names, registry)

        candidates = []
        best = None
        best_score = -float('inf')
        model_update_count = 0
        stop_reason = 'budget_exhausted'

        x_obs = []
        y_obs = []

        self.update_managed_run_progress(
            total_evaluations=budget,
            evaluations_completed=0,
            success_count=0,
            failure_count=0,
            phase='running',
            message=f"Optimizer surrogate_gp started (budget={budget}).",
        )

        try:
            for i in range(budget):
                abort_reason = self._should_abort_managed_run()
                if abort_reason:
                    stop_reason = abort_reason
                    break
                self.current_geometry_state = GeometryState.from_dict(original_state.to_dict())

                proposal_source = 'warmup_random'
                pred_mean = None
                pred_std = None
                pred_acq = None

                can_use_surrogate = i >= warmup_runs and len(y_obs) >= max(5, len(param_names) + 1)

                if can_use_surrogate:
                    x_train = np.asarray(x_obs, dtype=float)
                    y_train = np.asarray(y_obs, dtype=float)
                    gp_model = self._fit_gp_surrogate(x_train, y_train, noise=gp_noise)

                    if gp_model is not None:
                        model_update_count += 1
                        pool = np.zeros((candidate_pool_size, len(param_names)), dtype=float)
                        for j in range(candidate_pool_size):
                            for k, p in enumerate(param_names):
                                mn = float(registry[p]['bounds']['min'])
                                mx = float(registry[p]['bounds']['max'])
                                pool[j, k] = np_rng.uniform(mn, mx)

                        mu, std = self._gp_predict_with_uncertainty(gp_model, pool)
                        if direction == 'maximize':
                            acq = mu + exploration_beta * std
                        else:
                            acq = (-mu) + exploration_beta * std

                        best_idx = int(np.argmax(acq))
                        vec = np.clip(pool[best_idx], mins, maxs)
                        sample = self._vector_to_sample(param_names, vec)
                        proposal_source = 'surrogate_ucb'
                        pred_mean = float(mu[best_idx])
                        pred_std = float(std[best_idx])
                        pred_acq = float(acq[best_idx])
                    else:
                        sample = self._sample_random_candidate(param_names, registry, rng)
                else:
                    sample = self._sample_random_candidate(param_names, registry, rng)

                self.update_managed_run_progress(
                    current_run_index=i,
                    current_values=sample,
                    evaluations_completed=len(candidates),
                    success_count=sum(1 for c in candidates if c.get('success')),
                    failure_count=sum(1 for c in candidates if not c.get('success')),
                    phase='evaluating',
                    message=f"Evaluating candidate {i + 1}/{budget}",
                )

                run_record = self._evaluate_param_sample(study, sample, run_index=i, evaluator=evaluator)
                score = self._score_run_for_objective(run_record, objective_name, direction=direction)

                run_record['optimizer_score'] = score
                run_record['optimizer_raw_score'] = score
                run_record['optimizer_penalty'] = 0.0
                run_record['proposal_source'] = proposal_source
                if pred_mean is not None:
                    run_record['surrogate_pred_mean'] = pred_mean
                    run_record['surrogate_pred_std'] = pred_std
                    run_record['surrogate_acquisition'] = pred_acq

                candidates.append(run_record)

                obj_val = run_record.get('objectives', {}).get(objective_name)
                try:
                    obj_float = float(obj_val)
                    if np.isfinite(obj_float):
                        x_obs.append([float(sample[p]) for p in param_names])
                        y_obs.append(obj_float)
                except (TypeError, ValueError):
                    pass

                if score > best_score:
                    best_score = score
                    best = run_record

                self.update_managed_run_progress(
                    evaluations_completed=len(candidates),
                    success_count=sum(1 for c in candidates if c.get('success')),
                    failure_count=sum(1 for c in candidates if not c.get('success')),
                    phase='evaluating',
                    message=f"Completed candidate {i + 1}/{budget}",
                )
        finally:
            self.current_geometry_state = original_state
            self.recalculate_geometry_state()

        self.update_managed_run_progress(
            evaluations_completed=len(candidates),
            success_count=sum(1 for c in candidates if c.get('success')),
            failure_count=sum(1 for c in candidates if not c.get('success')),
            phase=stop_reason,
            current_values={},
            message=f"Optimizer surrogate_gp finished with status '{stop_reason}'.",
        )

        run_id = f"opt_{datetime.utcnow().strftime('%Y%m%dT%H%M%S_%f')}"
        summary = {
            'run_id': run_id,
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'study_name': study_name,
            'method': 'surrogate_gp',
            'seed': int(seed),
            'budget': budget,
            'max_budget_cap': self.MAX_OPTIMIZER_BUDGET,
            'objective': {
                'name': objective_name,
                'direction': direction,
            },
            'success_count': sum(1 for c in candidates if c.get('success')),
            'failure_count': sum(1 for c in candidates if not c.get('success')),
            'best_run': best,
            'candidates': candidates,
            'stop_reason': stop_reason,
            'evaluations_used': len(candidates),
            'generation_stats': [],
            'step_size_history': [],
            'surrogate': {
                'type': 'gp_rbf',
                'warmup_runs': warmup_runs,
                'candidate_pool_size': candidate_pool_size,
                'exploration_beta': exploration_beta,
                'gp_noise': gp_noise,
                'model_updates': model_update_count,
                'training_points': len(y_obs),
            },
        }

        self.current_geometry_state.optimizer_runs[run_id] = summary
        self._capture_history_state(f"Ran surrogate GP optimizer on study '{study_name}'")
        return summary, None

    def run_simulation_in_loop_optimizer(
        self,
        study_name,
        method='surrogate_gp',
        budget=20,
        seed=42,
        objective_name=None,
        direction=None,
        cmaes_config=None,
        surrogate_config=None,
        evaluator=None,
    ):
        if not callable(evaluator):
            return None, "A simulation evaluator callback is required."

        method = (method or 'surrogate_gp').strip().lower()

        if method == 'surrogate_gp':
            surrogate_cfg = surrogate_config or {}
            result, err = self.run_surrogate_param_optimizer(
                study_name=study_name,
                budget=budget,
                seed=seed,
                objective_name=objective_name,
                direction=direction,
                warmup_runs=surrogate_cfg.get('warmup_runs', 10),
                candidate_pool_size=surrogate_cfg.get('candidate_pool_size', 256),
                exploration_beta=surrogate_cfg.get('exploration_beta', 1.0),
                gp_noise=surrogate_cfg.get('gp_noise', 1e-6),
                evaluator=evaluator,
            )
        elif method in {'random_search', 'cmaes'}:
            result, err = self.run_param_optimizer(
                study_name=study_name,
                method=method,
                budget=budget,
                seed=seed,
                objective_name=objective_name,
                direction=direction,
                cmaes_config=cmaes_config,
                evaluator=evaluator,
            )
        else:
            return None, f"Unsupported simulation-in-loop method '{method}'."

        if result:
            result['simulation_in_loop'] = True
            result['simulation_method'] = method
        return result, err

    def _extract_best_objective_value(self, optimizer_result, objective_name):
        if not isinstance(optimizer_result, dict):
            return None
        best = optimizer_result.get('best_run') or {}
        objectives = best.get('objectives', {}) if isinstance(best, dict) else {}
        val = objectives.get(objective_name)
        try:
            x = float(val)
            if np.isfinite(x):
                return x
        except (TypeError, ValueError):
            return None
        return None

    def run_optimizer_head_to_head(
        self,
        study_name,
        budget=40,
        seed=42,
        objective_name=None,
        direction=None,
        classical_method='cmaes',
        cmaes_config=None,
        surrogate_config=None,
        evaluator=None,
    ):
        surrogate_cfg = surrogate_config or {}

        t0 = time.perf_counter()
        classical_result, classical_err = self.run_param_optimizer(
            study_name=study_name,
            method=classical_method,
            budget=budget,
            seed=seed,
            objective_name=objective_name,
            direction=direction,
            cmaes_config=cmaes_config,
            evaluator=evaluator,
        )
        classical_elapsed_s = float(time.perf_counter() - t0)
        if not classical_result:
            return None, classical_err or "Classical optimizer failed."

        resolved_objective = (classical_result.get('objective') or {}).get('name')
        resolved_direction = (classical_result.get('objective') or {}).get('direction', direction or 'maximize')

        t1 = time.perf_counter()
        surrogate_result, surrogate_err = self.run_surrogate_param_optimizer(
            study_name=study_name,
            budget=budget,
            seed=seed,
            objective_name=resolved_objective,
            direction=resolved_direction,
            warmup_runs=surrogate_cfg.get('warmup_runs', 10),
            candidate_pool_size=surrogate_cfg.get('candidate_pool_size', 256),
            exploration_beta=surrogate_cfg.get('exploration_beta', 1.0),
            gp_noise=surrogate_cfg.get('gp_noise', 1e-6),
            evaluator=evaluator,
        )
        surrogate_elapsed_s = float(time.perf_counter() - t1)
        if not surrogate_result:
            return None, surrogate_err or "Surrogate optimizer failed."

        obj_name = resolved_objective
        direction = resolved_direction or 'maximize'

        classical_best = self._extract_best_objective_value(classical_result, obj_name)
        surrogate_best = self._extract_best_objective_value(surrogate_result, obj_name)

        sign = 1.0 if direction == 'maximize' else -1.0
        winner = 'undetermined'
        delta_score = None
        relative_improvement_pct = None

        if classical_best is not None and surrogate_best is not None:
            c_score = sign * classical_best
            s_score = sign * surrogate_best
            delta_score = float(s_score - c_score)

            if abs(delta_score) < 1e-12:
                winner = 'tie'
            elif delta_score > 0:
                winner = 'surrogate'
            else:
                winner = 'classical'

            denom = abs(c_score)
            if denom > 1e-12:
                relative_improvement_pct = float((delta_score / denom) * 100.0)

        speedup_ratio = None
        if surrogate_elapsed_s > 1e-12:
            speedup_ratio = float(classical_elapsed_s / surrogate_elapsed_s)

        summary = {
            'study_name': study_name,
            'budget': int(budget),
            'seed': int(seed),
            'objective': {
                'name': obj_name,
                'direction': direction,
            },
            'classical': {
                'method': classical_method,
                'run_id': classical_result.get('run_id'),
                'elapsed_s': classical_elapsed_s,
                'evaluations_used': classical_result.get('evaluations_used', len(classical_result.get('candidates', []))),
                'success_count': classical_result.get('success_count'),
                'failure_count': classical_result.get('failure_count'),
                'best_objective': classical_best,
                'stop_reason': classical_result.get('stop_reason'),
            },
            'surrogate': {
                'method': surrogate_result.get('method', 'surrogate_gp'),
                'run_id': surrogate_result.get('run_id'),
                'elapsed_s': surrogate_elapsed_s,
                'evaluations_used': surrogate_result.get('evaluations_used', len(surrogate_result.get('candidates', []))),
                'success_count': surrogate_result.get('success_count'),
                'failure_count': surrogate_result.get('failure_count'),
                'best_objective': surrogate_best,
                'stop_reason': surrogate_result.get('stop_reason'),
                'config': surrogate_result.get('surrogate', {}),
            },
            'comparison': {
                'winner': winner,
                'delta_score_surrogate_minus_classical': delta_score,
                'relative_improvement_pct': relative_improvement_pct,
                'objective_delta_raw_surrogate_minus_classical': (None if (surrogate_best is None or classical_best is None) else float(surrogate_best - classical_best)),
                'speedup_ratio_classical_over_surrogate': speedup_ratio,
            },
            'run_ids': {
                'classical': classical_result.get('run_id'),
                'surrogate': surrogate_result.get('run_id'),
            },
            'details': {
                'classical_result': classical_result,
                'surrogate_result': surrogate_result,
            },
        }

        return summary, None

    def list_optimizer_runs(self, study_name=None, limit=50):
        if not self.current_geometry_state:
            return []
        runs = list((self.current_geometry_state.optimizer_runs or {}).values())
        runs.sort(key=lambda r: r.get('created_at', ''), reverse=True)
        if study_name:
            runs = [r for r in runs if r.get('study_name') == study_name]
        return runs[:max(1, int(limit))]

    def _get_optimizer_run(self, run_id):
        runs = (self.current_geometry_state.optimizer_runs or {}) if self.current_geometry_state else {}
        return runs.get(run_id)

    def run_param_optimizer(self, study_name, method='random_search', budget=20, seed=42, objective_name=None, direction=None, cmaes_config=None, evaluator=None):
        if not self.current_geometry_state:
            return None, "No active project state."

        studies = self.current_geometry_state.param_studies or {}
        if study_name not in studies:
            return None, f"Study '{study_name}' not found."

        study = studies[study_name]
        if method not in {'random_search', 'cmaes'}:
            return None, f"Unsupported optimizer method '{method}'."

        budget = max(1, int(budget))
        budget = min(budget, self.MAX_OPTIMIZER_BUDGET)
        seed = int(seed)

        objectives = study.get('objectives', []) or []
        if objective_name is None:
            objective_name = objectives[0].get('name', objectives[0].get('metric')) if objectives else 'success_flag'
        if direction is None:
            if objectives:
                for o in objectives:
                    nm = o.get('name', o.get('metric'))
                    if nm == objective_name:
                        direction = o.get('direction', 'maximize')
                        break
            if direction is None:
                direction = 'maximize'

        param_names = study.get('parameters', [])
        registry = self.current_geometry_state.parameter_registry

        original_state = GeometryState.from_dict(self.current_geometry_state.to_dict())
        algo_result = None

        try:
            self.current_geometry_state = GeometryState.from_dict(original_state.to_dict())
            if method == 'random_search':
                algo_result = self._run_random_search_optimizer(
                    study=study,
                    param_names=param_names,
                    registry=registry,
                    objective_name=objective_name,
                    direction=direction,
                    budget=budget,
                    seed=seed,
                    evaluator=evaluator,
                )
            else:
                algo_result = self._run_cmaes_optimizer(
                    study=study,
                    param_names=param_names,
                    registry=registry,
                    objective_name=objective_name,
                    direction=direction,
                    budget=budget,
                    seed=seed,
                    cmaes_config=cmaes_config,
                    evaluator=evaluator,
                )
        finally:
            self.current_geometry_state = original_state
            self.recalculate_geometry_state()

        candidates = algo_result.get('candidates', []) if isinstance(algo_result, dict) else []
        best = algo_result.get('best') if isinstance(algo_result, dict) else None

        run_id = f"opt_{datetime.utcnow().strftime('%Y%m%dT%H%M%S_%f')}"
        summary = {
            'run_id': run_id,
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'study_name': study_name,
            'method': method,
            'seed': seed,
            'budget': budget,
            'max_budget_cap': self.MAX_OPTIMIZER_BUDGET,
            'objective': {
                'name': objective_name,
                'direction': direction,
            },
            'success_count': sum(1 for c in candidates if c.get('success')),
            'failure_count': sum(1 for c in candidates if not c.get('success')),
            'best_run': best,
            'candidates': candidates,
            'stop_reason': algo_result.get('stop_reason') if isinstance(algo_result, dict) else None,
            'evaluations_used': algo_result.get('evaluations_used', len(candidates)) if isinstance(algo_result, dict) else len(candidates),
            'generation_stats': algo_result.get('generation_stats', []) if isinstance(algo_result, dict) else [],
            'step_size_history': algo_result.get('step_size_history', []) if isinstance(algo_result, dict) else [],
        }
        if method == 'cmaes' and isinstance(algo_result, dict):
            summary['cmaes'] = algo_result.get('cmaes', {})

        self.current_geometry_state.optimizer_runs[run_id] = summary
        self._capture_history_state(f"Ran optimizer '{method}' on study '{study_name}'")

        return summary, None

    def replay_optimizer_best_candidate(self, run_id, apply_to_project=True):
        if not self.current_geometry_state:
            return None, "No active project state."

        opt_run = self._get_optimizer_run(run_id)
        if not opt_run:
            return None, f"Optimizer run '{run_id}' not found."

        study_name = opt_run.get('study_name')
        studies = self.current_geometry_state.param_studies or {}
        if study_name not in studies:
            return None, f"Study '{study_name}' referenced by optimizer run not found."

        best = opt_run.get('best_run') or {}
        best_values = best.get('values')
        if not isinstance(best_values, dict) or not best_values:
            return None, "Optimizer run has no best candidate values to replay."

        study = studies[study_name]
        original_state = GeometryState.from_dict(self.current_geometry_state.to_dict())

        try:
            run_record = self._evaluate_param_sample(study, dict(best_values), run_index=0)
            replay_record = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'run_id': run_id,
                'success': bool(run_record.get('success')),
                'error': run_record.get('error'),
                'objective_values': run_record.get('objectives', {}),
                'optimizer_score': run_record.get('optimizer_score'),
            }

            opt_run.setdefault('replay_records', []).append(replay_record)

            if apply_to_project:
                self._capture_history_state(f"Replayed best candidate from optimizer run '{run_id}'")
                return {
                    'run_id': run_id,
                    'applied_to_project': True,
                    'replay_record': replay_record,
                    'run_record': run_record,
                }, None

            # not applying: restore previous state
            self.current_geometry_state = original_state
            self.recalculate_geometry_state()
            return {
                'run_id': run_id,
                'applied_to_project': False,
                'replay_record': replay_record,
                'run_record': run_record,
            }, None
        except Exception as e:
            self.current_geometry_state = original_state
            self.recalculate_geometry_state()
            return None, str(e)

    def verify_optimizer_best_candidate(self, run_id, repeats=3):
        if not self.current_geometry_state:
            return None, "No active project state."

        opt_run = self._get_optimizer_run(run_id)
        if not opt_run:
            return None, f"Optimizer run '{run_id}' not found."

        study_name = opt_run.get('study_name')
        studies = self.current_geometry_state.param_studies or {}
        if study_name not in studies:
            return None, f"Study '{study_name}' referenced by optimizer run not found."

        best = opt_run.get('best_run') or {}
        best_values = best.get('values')
        if not isinstance(best_values, dict) or not best_values:
            return None, "Optimizer run has no best candidate values to verify."

        repeats = max(1, min(int(repeats), 100))
        objective = opt_run.get('objective', {}) or {}
        objective_name = objective.get('name')

        study = studies[study_name]
        original_state = GeometryState.from_dict(self.current_geometry_state.to_dict())

        verification_runs = []
        stop_reason = 'completed'
        try:
            for i in range(repeats):
                abort_reason = self._should_abort_managed_run()
                if abort_reason:
                    stop_reason = abort_reason
                    break

                self.current_geometry_state = GeometryState.from_dict(original_state.to_dict())
                rr = self._evaluate_param_sample(study, dict(best_values), run_index=i)
                verification_runs.append(rr)
        finally:
            self.current_geometry_state = original_state
            self.recalculate_geometry_state()

        obj_values = []
        if objective_name:
            for rr in verification_runs:
                val = rr.get('objectives', {}).get(objective_name)
                try:
                    obj_values.append(float(val))
                except (TypeError, ValueError):
                    pass

        if obj_values:
            stats = {
                'count': len(obj_values),
                'mean': float(np.mean(obj_values)),
                'std': float(np.std(obj_values)),
                'min': float(np.min(obj_values)),
                'max': float(np.max(obj_values)),
            }
        else:
            stats = {'count': 0, 'mean': None, 'std': None, 'min': None, 'max': None}

        verification_record = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'run_id': run_id,
            'requested_repeats': repeats,
            'repeats': len(verification_runs),
            'objective_name': objective_name,
            'stats': stats,
            'stop_reason': stop_reason,
            'success_count': sum(1 for r in verification_runs if r.get('success')),
            'failure_count': sum(1 for r in verification_runs if not r.get('success')),
        }
        opt_run.setdefault('verification_records', []).append(verification_record)

        return {
            'run_id': run_id,
            'objective_name': objective_name,
            'verification_record': verification_record,
            'stop_reason': stop_reason,
            'runs': verification_runs,
        }, None

    def get_object_details(self, object_type, object_name_or_id):
        """
        Get details for a specific object by its type and name/ID.
        'object_type' can be 'define', 'material', 'solid', 'logical_volume', 'physical_volume',
        'environment', 'scoring', or 'detector_feature_generator'.
        For 'physical_volume', object_name_or_id would be its unique ID.
        """
        if not self.current_geometry_state: return None
        
        state = self.current_geometry_state
        obj = None

        if object_type == "define": 
            obj = state.defines.get(object_name_or_id)
        elif object_type == "material": 
            obj = state.materials.get(object_name_or_id)
        elif object_type == "element": 
            obj = state.elements.get(object_name_or_id)
        elif object_type == "isotope": 
            obj = state.isotopes.get(object_name_or_id)
        elif object_type == "solid": 
            obj = state.solids.get(object_name_or_id)
        elif object_type == "logical_volume": 
            obj = state.logical_volumes.get(object_name_or_id)
        elif object_type == "assembly":
            obj = state.assemblies.get(object_name_or_id)
        elif object_type == "optical_surface":
            obj = state.optical_surfaces.get(object_name_or_id)
        elif object_type == "skin_surface":
            obj = state.skin_surfaces.get(object_name_or_id)
        elif object_type == "border_surface":
            obj = state.border_surfaces.get(object_name_or_id)
        elif object_type == "environment":
            obj = state.environment
        elif object_type == "scoring":
            obj = state.scoring
        elif object_type == "detector_feature_generator":
            obj = self.get_detector_feature_generator_details(object_name_or_id)
        elif object_type == "physical_volume":
            # Search through all logical volumes to find the PV
            all_lvs = list(state.logical_volumes.values())
            for lv in all_lvs:
                # We only search in LVs that contain physical placements
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.id == object_name_or_id:
                            obj = pv
                            break
                if obj:
                    break
            
            # Also search through assemblies (important for completeness)
            if not obj:
                all_asms = list(state.assemblies.values())
                for asm in all_asms:
                    for pv in asm.placements:
                        if pv.id == object_name_or_id:
                            obj = pv
                            break
                    if obj:
                        break
        
        elif object_type == "particle_source":
            # Search in sources dict. 
            for s in state.sources.values():
                if s.id == object_name_or_id or s.name == object_name_or_id:
                    obj = s
                    break

        if isinstance(obj, dict):
            return deepcopy(obj)
        return obj.to_dict() if obj else None

    def _normalize_update_property_path_parts(self, property_path):
        if not isinstance(property_path, str):
            return None, f"Invalid property path '{property_path}'"

        normalized_property_path = property_path.strip()
        if not normalized_property_path:
            return None, f"Invalid property path '{property_path}'"

        path_parts = normalized_property_path.split('.')
        if any(not part for part in path_parts):
            return None, f"Invalid property path '{property_path}'"

        return path_parts, None

    def _environment_field_descriptor(self, target_obj):
        field_name = getattr(target_obj.__class__, "ENVIRONMENT_FIELD_NAME", None)
        vector_name = getattr(target_obj.__class__, "FIELD_VECTOR_NAME", None)

        if not field_name:
            field_name = (
                "environment.local_uniform_magnetic_field"
                if hasattr(target_obj, "target_volume_names")
                else "environment.global_uniform_magnetic_field"
            )

        if not vector_name:
            vector_name = "field_vector_tesla"

        return field_name, vector_name

    def _normalize_environment_update_value(self, target_obj, property_path, new_value):
        field_name, vector_name = self._environment_field_descriptor(target_obj)

        if property_path == 'enabled':
            if isinstance(new_value, bool):
                return new_value, None

            if isinstance(new_value, str):
                normalized = new_value.strip().lower()
                if normalized in {'true', '1', 'yes', 'on'}:
                    return True, None
                if normalized in {'false', '0', 'no', 'off'}:
                    return False, None

            return None, f"{field_name}.enabled must be a boolean."

        string_properties = getattr(target_obj.__class__, "ENVIRONMENT_STRING_PROPERTIES", set())
        if property_path in string_properties:
            if new_value is None:
                return None, f"{field_name}.{property_path} must be a non-empty string."

            normalized = str(new_value).strip()
            if not normalized:
                return None, f"{field_name}.{property_path} must be a non-empty string."

            return normalized, None

        if property_path == 'target_volume_names':
            if not hasattr(target_obj, "target_volume_names"):
                return None, f"Invalid property path '{property_path}'"

            if new_value is None:
                return [], None

            if isinstance(new_value, str):
                raw_items = re.split(r"[,\n;]+", new_value)
            elif isinstance(new_value, (list, tuple, set)):
                raw_items = list(new_value)
            else:
                return None, f"{field_name}.target_volume_names must be an array of strings."

            normalized = []
            seen = set()
            for raw_item in raw_items:
                name = str(raw_item).strip()
                if not name or name in seen:
                    continue
                normalized.append(name)
                seen.add(name)

            return normalized, None

        numeric_properties = getattr(target_obj.__class__, "ENVIRONMENT_NUMERIC_PROPERTIES", set())
        if property_path in numeric_properties:
            try:
                numeric_value = float(new_value)
            except (TypeError, ValueError):
                return None, f"{field_name}.{property_path} must be a finite number."

            if not math.isfinite(numeric_value):
                return None, f"{field_name}.{property_path} must be a finite number."

            return numeric_value, None

        if property_path.startswith(f'{vector_name}.'):
            axis = property_path.split('.', 1)[1]
            if axis not in {'x', 'y', 'z'}:
                return None, f"Invalid property path '{property_path}'"

            try:
                numeric_value = float(new_value)
            except (TypeError, ValueError):
                return None, f"{field_name}.{vector_name}.{axis} must be a finite number."

            if not math.isfinite(numeric_value):
                return None, f"{field_name}.{vector_name}.{axis} must be a finite number."

            return numeric_value, None

        return None, f"Invalid property path '{property_path}'"

    def _normalize_scoring_update_value(self, target_obj, property_path, new_value):
        if not isinstance(target_obj, ScoringState):
            return None, f"Invalid scoring state target for property path '{property_path}'"

        candidate_state = target_obj.to_dict()

        if property_path == 'state':
            if not isinstance(new_value, dict):
                return None, "scoring must be an object."
            candidate_state = deepcopy(new_value)
        elif property_path in {'schema_version', 'scoring_meshes', 'tally_requests', 'run_manifest_defaults'}:
            candidate_state[property_path] = deepcopy(new_value)
        else:
            return None, f"Invalid property path '{property_path}'"

        is_valid, validation_error = ScoringState.validate(candidate_state, field_name='scoring')
        if not is_valid:
            return None, validation_error

        return ScoringState.from_dict(candidate_state), None

    def update_object_property(self, object_type, object_id, property_path, new_value):
        """
        Updates a property of an object.
        object_id: unique ID for Solids, LVs, PVs. For Defines/Materials, it's their name.
        property_path: e.g., "name", "parameters.x", "position.x"
        """
        # This needs careful implementation to find the object and update its property.
        # Example for a physical volume's position.x:
        if not self.current_geometry_state: return False
        print(f"Attempting to update: Type='{object_type}', ID/Name='{object_id}', Path='{property_path}', NewValue='{new_value}'")

        target_obj = None

        # Handle all possible object types.
        if object_type == "define": target_obj = self.current_geometry_state.defines.get(object_id)
        elif object_type == "material": target_obj = self.current_geometry_state.materials.get(object_id)
        elif object_type == "solid": target_obj = self.current_geometry_state.solids.get(object_id)
        elif object_type == "logical_volume": target_obj = self.current_geometry_state.logical_volumes.get(object_id)
        elif object_type == "environment":
            environment_objects = {
                "global_uniform_magnetic_field": self.current_geometry_state.environment.global_uniform_magnetic_field,
                "global_uniform_electric_field": self.current_geometry_state.environment.global_uniform_electric_field,
                "local_uniform_magnetic_field": self.current_geometry_state.environment.local_uniform_magnetic_field,
                "local_uniform_electric_field": self.current_geometry_state.environment.local_uniform_electric_field,
                "region_cuts_and_limits": self.current_geometry_state.environment.region_cuts_and_limits,
            }
            target_obj = environment_objects.get(object_id)
            if target_obj is None:
                return False, f"Could not find object of type '{object_type}' with ID/Name '{object_id}'"
        elif object_type == "scoring":
            if object_id != "scoring_state":
                return False, f"Could not find object of type '{object_type}' with ID/Name '{object_id}'"
            target_obj = self.current_geometry_state.scoring
        elif object_type == "physical_volume":

            # Iterate through LVs and Assemblies
            all_lvs = list(self.current_geometry_state.logical_volumes.values())
            for lv in all_lvs:
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.id == object_id:
                            target_obj = pv
                            break
                if target_obj: break
            
            if not target_obj:
                all_asms = list(self.current_geometry_state.assemblies.values())
                for asm in all_asms:
                    for pv in asm.placements:
                        if pv.id == object_id:
                            target_obj = pv
                            break
                    if target_obj: break

        if not target_obj: 
            return False, f"Could not find object of type '{object_type}' with ID/Name '{object_id}'"

        path_parts, path_error = self._normalize_update_property_path_parts(property_path)
        if path_error:
            return False, path_error

        try:
            if object_type == "environment":
                new_value, coercion_error = self._normalize_environment_update_value(target_obj, property_path, new_value)
                if coercion_error:
                    return False, coercion_error
            elif object_type == "scoring":
                next_scoring_state, coercion_error = self._normalize_scoring_update_value(
                    target_obj,
                    property_path,
                    new_value,
                )
                if coercion_error:
                    return False, coercion_error
                self.current_geometry_state.scoring = next_scoring_state
                target_obj = next_scoring_state
                path_parts = None

            if path_parts is not None:
                current_level_obj = target_obj
                for part in path_parts[:-1]:
                    if isinstance(current_level_obj, dict):
                        current_level_obj = current_level_obj[part]
                    else:
                        current_level_obj = getattr(current_level_obj, part)

                final_key = path_parts[-1]
                if isinstance(current_level_obj, dict):
                    current_level_obj[final_key] = new_value
                else:
                    setattr(current_level_obj, final_key, new_value)
        except (AttributeError, KeyError, TypeError, IndexError) as e:
            return False, f"Invalid property path '{property_path}': {e}"
        
        # Capture the new state
        self._capture_history_state(f"Updated {property_path} of {object_type} {object_id}")

        success, error_msg = self.recalculate_geometry_state()
        if not success:
            # Add logic here to revert the change?
            return False, f"Update failed during recalculation: {error_msg}"
        return True, None

    def add_define(self, name_suggestion, define_type, raw_expression, unit=None, category=None):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.defines)
        new_define = Define(name, define_type, raw_expression, unit, category)
        self.current_geometry_state.add_define(new_define)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added define {name}")

        return new_define.to_dict(), None

    def update_define(self, define_name, new_raw_expression, new_unit=None, new_category=None):
        if not self.current_geometry_state:
            return False, "No project loaded."

        target_define = self.current_geometry_state.defines.get(define_name)
        if not target_define:
            return False, f"Define '{define_name}' not found."
            
        target_define.raw_expression = new_raw_expression
        
        if new_unit is not None: 
            target_define.unit = new_unit
        if new_category is not None: 
            target_define.category = new_category

        # Capture the new state
        self._capture_history_state(f"Updated define {define_name}")

        success, error_msg = self.recalculate_geometry_state()
        return success, error_msg

    def add_material(self, name_suggestion, properties_dict):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.materials)
        
        # Check if this is a NIST material name (starts with G4_)
        # If it's a NIST name and has no components/Z/A/density, create as NIST material
        is_nist_name = name_suggestion.startswith("G4_")
        has_no_components = not properties_dict.get('components')
        has_no_z = not properties_dict.get('Z_expr') and not properties_dict.get('Z')
        has_no_a = not properties_dict.get('A_expr') and not properties_dict.get('A')
        has_no_density = not properties_dict.get('density_expr') and not properties_dict.get('density')
        
        if is_nist_name and has_no_components and has_no_z:
            # Create as NIST material - this tells Geant4 to use the built-in material
            properties_dict = {**properties_dict, 'mat_type': 'nist'}
        
        # Auto-create missing elements referenced in components
        components = properties_dict.get('components', [])
        if components:
            for comp in components:
                ref_name = comp.get('ref', '')
                if ref_name and ref_name not in self.current_geometry_state.elements:
                    # Try to look up Z from periodic table
                    ref_lower = ref_name.lower().strip()
                    Z = getattr(self, '_get_element_z', lambda x: None)(ref_lower)
                    if Z is None:
                        # Check PERIODIC_TABLE from geometry_types
                        from .geometry_types import PERIODIC_TABLE
                        Z = PERIODIC_TABLE.get(ref_lower)
                    
                    # Create a simple element with the referenced name
                    new_element = Element(name=ref_name, Z=Z)
                    self.current_geometry_state.elements[ref_name] = new_element
        
        # Assumes properties_dict contains expression strings like Z_expr, A_expr, density_expr
        new_material = Material(name, **properties_dict)
        self.current_geometry_state.add_material(new_material)
        success, error_msg = self.recalculate_geometry_state()
        if not success:
            del self.current_geometry_state.materials[name]
            self.recalculate_geometry_state()
            return None, error_msg

        # Capture the new state
        self._capture_history_state(f"Added material {name}")

        return new_material.to_dict(), None

    def update_material(self, mat_name, new_properties):
        if not self.current_geometry_state: return False, "No project loaded"
        target_mat = self.current_geometry_state.materials.get(mat_name)
        if not target_mat: return False, f"Material '{mat_name}' not found."

        old_values = {
            'mat_type': target_mat.mat_type,
            'Z_expr': target_mat.Z_expr,
            'A_expr': target_mat.A_expr,
            'density_expr': target_mat.density_expr,
            'state': target_mat.state,
            'components': deepcopy(target_mat.components),
        }

        # Update properties from the provided dictionary
        # if 'density' in new_properties: target_mat.density = new_properties['density']
        # if 'Z' in new_properties: target_mat.Z = new_properties['Z']
        # if 'A' in new_properties: target_mat.A = new_properties['A']
        # if 'components' in new_properties: target_mat.components = new_properties['components']
        for key, value in new_properties.items(): setattr(target_mat, key, value)

        success, error_msg = self.recalculate_geometry_state()
        if not success:
            for key, value in old_values.items():
                setattr(target_mat, key, value)
            self.recalculate_geometry_state()
            return False, error_msg

        # Capture the new state
        self._capture_history_state(f"Updated material {mat_name}")
        return True, None

    def add_element(self, name_suggestion, params):
        """Adds a new element to the project."""
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.elements)
        
        new_element = Element(
            name=name,
            formula=params.get('formula'),
            Z=params.get('Z'),
            A_expr=params.get('A_expr'),
            components=params.get('components', [])
        )
        
        self.current_geometry_state.add_element(new_element)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added element {name}")
        
        return new_element.to_dict(), None

    def update_element(self, element_name, new_params):
        """Updates an existing element."""
        if not self.current_geometry_state:
            return False, "No project loaded"
        
        target_element = self.current_geometry_state.elements.get(element_name)
        if not target_element:
            return False, f"Element '{element_name}' not found."

        target_element.formula = new_params.get('formula', target_element.formula)
        target_element.Z = new_params.get('Z', target_element.Z)
        target_element.A_expr = new_params.get('A_expr', target_element.A_expr)
        target_element.components = new_params.get('components', target_element.components)

        # Capture the new state
        self._capture_history_state(f"Updated element {element_name}")

        self.recalculate_geometry_state()
        return True, None

    def add_isotope(self, name_suggestion, params):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.isotopes)
        new_isotope = Isotope(name, Z=params.get('Z'), N=params.get('N'), A_expr=params.get('A_expr'))
        self.current_geometry_state.add_isotope(new_isotope)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added isotope {name}")

        return new_isotope.to_dict(), None

    def update_isotope(self, isotope_name, new_params):
        if not self.current_geometry_state: return False, "No project loaded"
        target_isotope = self.current_geometry_state.isotopes.get(isotope_name)
        if not target_isotope: return False, f"Isotope '{isotope_name}' not found."
        target_isotope.Z = new_params.get('Z', target_isotope.Z)
        target_isotope.N = new_params.get('N', target_isotope.N)
        target_isotope.A_expr = new_params.get('A_expr', target_isotope.A_expr)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated isotope {isotope_name}")

        return True, None

    def add_solid(self, name_suggestion, solid_type, raw_parameters):
        """
        Adds a new solid to the project.
        """
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        # Start with a clear change tracker
        self._clear_change_tracker()
        
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.solids)
        new_solid = Solid(name, solid_type, raw_parameters)
        self.current_geometry_state.add_solid(new_solid)

        # Set the new solid as "changed" so it is sent to the front end for sure
        self.changed_object_ids['solids'].add(name)

        # Capture the new state
        self._capture_history_state(f"Added solid {name}")
        
        return new_solid.to_dict(), None

    def update_solid(self, solid_id, new_raw_parameters):
        """Updates the raw parameters of an existing primitive solid."""
        if not self.current_geometry_state:
            return False, "No project loaded."
        
        target_solid = self.current_geometry_state.solids.get(solid_id)
        if not target_solid:
            return False, f"Solid '{solid_id}' not found."
            
        if target_solid.type == 'boolean':
            return False, "Boolean solids must be updated via the 'update_boolean_solid' method."
            
        target_solid.raw_parameters = new_raw_parameters

        # Capture the new state
        self._capture_history_state(f"Added standard solid {solid_id}")
        
        success, error_msg = self.recalculate_geometry_state()
        return success, error_msg

    def add_boolean_solid(self, name_suggestion, recipe):
        """
        Creates a single 'virtual' boolean solid that stores the recipe.
        """
        if not self.current_geometry_state: return False, "No project loaded."
        if len(recipe) < 2 or recipe[0].get('op') != 'base':
            return False, "Invalid recipe format."

        for item in recipe:
            ref = item.get('solid_ref')
            if not ref or ref not in self.current_geometry_state.solids:
                return False, f"Solid '{ref}' not found in project."

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.solids)
        params = {"recipe": recipe}
        new_solid = Solid(name, "boolean", params)
        self.current_geometry_state.add_solid(new_solid)

        # Capture the new state
        self._capture_history_state(f"Added boolean solid {name}")
        
        return new_solid.to_dict(), None

    def update_boolean_solid(self, solid_name, new_recipe):
        """
        Updates an existing boolean solid with a new recipe.
        """
        if not self.current_geometry_state: return False, "No project loaded."
        
        target_solid = self.current_geometry_state.solids.get(solid_name)
        if not target_solid or target_solid.type != 'boolean':
            return False, f"Boolean solid '{solid_name}' not found."

        # Validate new recipe
        for item in new_recipe:
            ref = item.get('solid_ref')
            if not ref or ref not in self.current_geometry_state.solids:
                return False, f"Solid '{ref}' not found in project."

        target_solid.raw_parameters['recipe'] = new_recipe
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated boolean solid {solid_name}")

        return True, None

    def add_solid_and_place(self, solid_params, lv_params, pv_params):
        """
        Handles both primitive and boolean solid creation.
        """
        if not self.current_geometry_state:
            return False, "No project loaded."

        solid_name_sugg = solid_params['name']
        solid_type = solid_params['type']
        
        new_solid_dict = None
        solid_error = None

        # --- 1. Add the Solid (dispatch based on type) ---
        if solid_type == 'boolean':
            recipe = solid_params['recipe']
            new_solid_dict, solid_error = self.add_boolean_solid(solid_name_sugg, recipe)
        else:
            solid_raw_params = solid_params['params']
            new_solid_dict, solid_error = self.add_solid(solid_name_sugg, solid_type, solid_raw_params)
        
        if solid_error:
            return False, f"Failed to create solid: {solid_error}"
        
        new_solid_name = new_solid_dict['name']

        # --- 2. Add the Logical Volume (if requested) ---
        if not lv_params:
            
            # Capture the new state
            self._capture_history_state(f"Added solid {new_solid_name}, no LV or PV")

            self.recalculate_geometry_state() # Recalculate just before returning
            return True, None
            
        lv_name_sugg = lv_params.get('name', f"{new_solid_name}_lv")
        material_ref = lv_params.get('material_ref')

        new_lv_dict, lv_error = self.add_logical_volume(lv_name_sugg, new_solid_name, material_ref)
        if lv_error:
            return False, f"Failed to create logical volume: {lv_error}"
            
        new_lv_name = new_lv_dict['name']

        # --- 3. Add the Physical Volume Placement (if requested) ---
        if not pv_params:

            # Capture the new state
            self._capture_history_state(f"Added solid {new_solid_name} and LV {new_lv_name}, no PV")

            self.recalculate_geometry_state()
            return True, None
            
        parent_lv_name = pv_params.get('parent_lv_name')
        if not parent_lv_name:
             return False, "Parent logical volume for placement was not specified."
        
        pv_name_sugg = pv_params.get('name', f"{new_lv_name}_PV")
        position = {'x': '0', 'y': '0', 'z': '0'} 
        rotation = {'x': '0', 'y': '0', 'z': '0'}
        scale    = {'x': '1', 'y': '1', 'z': '1'}

        new_pv_dict, pv_error = self.add_physical_volume(parent_lv_name, pv_name_sugg, new_lv_name, position, rotation, scale)
        if pv_error:
            return False, f"Failed to place physical volume: {pv_error}"
        
        new_pv_name = new_pv_dict['name']
        
        # Capture the new state
        self._capture_history_state(f"Added solid {new_solid_name}, LV {new_lv_name}, PV {new_pv_name}")
        
        self.recalculate_geometry_state()
        return True, None

    def add_logical_volume(self, name_suggestion, solid_ref, material_ref, 
                           vis_attributes=None, is_sensitive=False,
                           content_type='physvol', content=None):
        
        if not self.current_geometry_state: return None, "No project loaded"
        if solid_ref not in self.current_geometry_state.solids:
            return None, f"Solid '{solid_ref}' not found."
        if material_ref not in self.current_geometry_state.materials:
            return None, f"Material '{material_ref}' not found."

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.logical_volumes)
        new_lv = LogicalVolume(name, solid_ref, material_ref, vis_attributes, is_sensitive)

        new_lv.content_type = content_type
        if content_type == 'replica':
            new_lv.content = ReplicaVolume.from_dict(content)
        elif content_type == 'division':
            new_lv.content = DivisionVolume.from_dict(content)
        else: # physvol
            new_lv.content = [] # It's a new, empty standard LV

        self.current_geometry_state.add_logical_volume(new_lv)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added LV {name}")

        return new_lv.to_dict(), None        

    def update_logical_volume(self, lv_name, new_solid_ref, new_material_ref, 
                              new_vis_attributes=None, new_is_sensitive=None,
                              new_content_type=None, new_content=None):
        if not self.current_geometry_state: return False, "No project loaded"
        
        lv = self.current_geometry_state.logical_volumes.get(lv_name)
        if not lv:
            return False, f"Logical Volume '{lv_name}' not found."

        success, error_msg = self._apply_logical_volume_update(
            lv,
            new_solid_ref=new_solid_ref,
            new_material_ref=new_material_ref,
            new_vis_attributes=new_vis_attributes,
            new_is_sensitive=new_is_sensitive,
            new_content_type=new_content_type,
            new_content=new_content,
            strict=False,
        )
        if not success:
            return False, error_msg

        # Capture the new state
        self._capture_history_state(f"Updated LV {lv_name}")

        self.recalculate_geometry_state()
        return True, None

    def _apply_logical_volume_update(
        self,
        lv,
        new_solid_ref=None,
        new_material_ref=None,
        new_vis_attributes=None,
        new_is_sensitive=None,
        new_content_type=None,
        new_content=None,
        strict=False,
    ):
        """Apply a logical-volume update in-place, optionally validating references."""
        if not self.current_geometry_state or lv is None:
            return False, "No project loaded."

        if new_solid_ref is not None:
            if new_solid_ref in self.current_geometry_state.solids:
                lv.solid_ref = new_solid_ref
            elif strict:
                return False, f"Solid '{new_solid_ref}' not found."

        if new_material_ref is not None:
            if new_material_ref in self.current_geometry_state.materials:
                lv.material_ref = new_material_ref
            elif strict:
                return False, f"Material '{new_material_ref}' not found."

        if new_vis_attributes is not None:
            lv.vis_attributes = new_vis_attributes

        if new_is_sensitive is not None:
            lv.is_sensitive = bool(new_is_sensitive)

        if new_content_type and new_content is not None and len(new_content) > 0:
            lv.content_type = new_content_type
            if new_content_type == 'replica':
                lv.content = ReplicaVolume.from_dict(new_content)
            elif new_content_type == 'division':
                lv.content = DivisionVolume.from_dict(new_content)
            elif new_content_type == 'parameterised':
                lv.content = ParamVolume.from_dict(new_content)
            else:
                lv.content = []

        return True, None

    def update_logical_volume_batch(self, updates_list):
        """Apply a batch of logical-volume updates atomically."""
        if not self.current_geometry_state:
            return False, "No project loaded.", []

        if not isinstance(updates_list, list):
            return False, "Invalid request: 'updates' must be a list.", []

        normalized_updates = []
        for index, update_data in enumerate(updates_list):
            if not isinstance(update_data, dict):
                return False, f"Logical volume update #{index + 1} must be an object.", []

            lv_ref = update_data.get('id')
            if lv_ref is None:
                lv_ref = update_data.get('name')

            lv_name = self._resolve_logical_volume_name(lv_ref)
            if not lv_name:
                return False, f"Logical Volume '{lv_ref}' not found.", []

            new_solid_ref = update_data.get('solid_ref')
            if isinstance(new_solid_ref, str):
                new_solid_ref = new_solid_ref.strip() or None

            new_material_ref = update_data.get('material_ref')
            if isinstance(new_material_ref, str):
                new_material_ref = new_material_ref.strip() or None

            if new_solid_ref is not None and new_solid_ref not in self.current_geometry_state.solids:
                return False, f"Solid '{new_solid_ref}' not found.", []

            if new_material_ref is not None and new_material_ref not in self.current_geometry_state.materials:
                return False, f"Material '{new_material_ref}' not found.", []

            normalized_updates.append((
                self.current_geometry_state.logical_volumes[lv_name],
                lv_name,
                new_solid_ref,
                new_material_ref,
                update_data.get('vis_attributes'),
                update_data.get('is_sensitive'),
                update_data.get('content_type'),
                update_data.get('content'),
            ))

        if not normalized_updates:
            return True, None, []

        self.begin_transaction()
        updated_lv_names = []

        try:
            for lv, lv_name, new_solid_ref, new_material_ref, new_vis_attributes, new_is_sensitive, new_content_type, new_content in normalized_updates:
                success, error_msg = self._apply_logical_volume_update(
                    lv,
                    new_solid_ref=new_solid_ref,
                    new_material_ref=new_material_ref,
                    new_vis_attributes=new_vis_attributes,
                    new_is_sensitive=new_is_sensitive,
                    new_content_type=new_content_type,
                    new_content=new_content,
                    strict=True,
                )
                if not success:
                    raise ValueError(error_msg)
                if lv_name not in updated_lv_names:
                    updated_lv_names.append(lv_name)

            success, error_msg = self.recalculate_geometry_state()
            if not success:
                raise ValueError(error_msg)
        except Exception as exc:
            self.abort_transaction()
            return False, str(exc), []

        self.end_transaction(f"Batch update to {len(updated_lv_names)} logical volumes")
        return True, None, updated_lv_names

    def add_physical_volume(self, parent_lv_name, pv_name_suggestion, placed_lv_ref, position, rotation, scale, copy_number_expr="0"):
        if not self.current_geometry_state: return None, "No project loaded"
        
        state = self.current_geometry_state

        # Find the parent LV
        parent_lv = state.logical_volumes.get(parent_lv_name)
        if not parent_lv:
            return None, f"Parent Logical Volume '{parent_lv_name}' not found."
        
        # A placed reference can be either a Logical Volume OR an Assembly.
        is_lv = placed_lv_ref in state.logical_volumes
        is_assembly = placed_lv_ref in state.assemblies
        if not is_lv and not is_assembly:
            return None, f"Placed Volume or Assembly '{placed_lv_ref}' not found."

        # Generate a unique name for this PV *within its parent* (GDML PV names are not global)
        # For simplicity, we'll use a globally unique suggested name for now.
        # A better approach for pv_name would be to ensure it's unique among siblings.
        pv_name = pv_name_suggestion or f"{placed_lv_ref}_placement"

        # position_dict and rotation_dict are assumed to be {'x':val,...} in internal units
        new_pv = PhysicalVolumePlacement(pv_name, placed_lv_ref,
                                        parent_lv_name=parent_lv_name,
                                        copy_number_expr=copy_number_expr,
                                        position_val_or_ref=position,
                                        rotation_val_or_ref=rotation,
                                        scale_val_or_ref=scale)
        parent_lv.add_child(new_pv)
        
        # Capture the new state
        self._capture_history_state(f"Added PV {pv_name}")

        self.recalculate_geometry_state()
        return new_pv.to_dict(), None

    def update_physical_volume(self, pv_id, new_name, new_position, new_rotation, new_scale):
        if not self.current_geometry_state: return False, "No project loaded"
        
        # Create an updates list of a single element.
        update = [{
                    "id": pv_id,
                    "name": new_name,
                    "position": new_position,
                    "rotation": new_rotation,
                    "scale": new_scale
                 }]
        
        # Call the batched update function.
        return self.update_physical_volume_batch(update)
    
    def _update_single_pv(self, pv_id, new_name, new_position, new_rotation, new_scale):
        pv_to_update = None

        # Search through all logical volumes and their new 'content' list
        all_lvs = list(self.current_geometry_state.logical_volumes.values())
        for lv in all_lvs:
            if lv.content_type == 'physvol':
                for pv in lv.content:
                    if pv.id == pv_id:
                        pv_to_update = pv
                        break
            if pv_to_update:
                break
        
        # Also search assemblies
        if not pv_to_update:
            all_asms = list(self.current_geometry_state.assemblies.values())
            for asm in all_asms:
                for pv in asm.placements:
                    if pv.id == pv_id:
                        pv_to_update = pv
                        break
                if pv_to_update:
                    break
        
        if not pv_to_update:
            return None
            
        if new_name is not None: pv_to_update.name = new_name
        if new_position is not None: pv_to_update.position = new_position
        if new_rotation is not None: pv_to_update.rotation = new_rotation
        if new_scale is not None: pv_to_update.scale = new_scale

        return pv_to_update
    
    def update_physical_volume_batch(self, updates_list):
        """
        Updates a batch of physical volumes' transforms in a single transaction.
        updates_list: A list of dictionaries, each with 'id', 'name', 'position', 'rotation', 'scale'.
        """
        if not self.current_geometry_state:
            return False, "No project loaded."
        
        updated_pv_objects = []
        
        try:
            # Apply all updates.
            for update_data in updates_list:
                pv_id = update_data.get('id')
                if not pv_id: continue

                new_name = update_data.get('name')
                new_position = update_data.get('position')
                new_rotation = update_data.get('rotation')
                new_scale = update_data.get('scale')

                updated_pv = self._update_single_pv(pv_id, new_name, new_position, new_rotation, new_scale)
                updated_pv_objects.append(updated_pv)
                
            # After all updates are applied, recalculate the entire state
            success, error_msg = self.recalculate_geometry_state()
            if not success:
                return False, error_msg

            # --- Sync Bound Sources ---
            # If any PV is moved, it might be a parent/ancestor of a bound volume (e.g. Assembly placement).
            # To ensure consistency, we update ALL bound sources.
            # This is computationally cheap enough (usually < 100 sources) and guarantees correctness without complex tree traversal checks.
            sources_updated = []
            for source in self.current_geometry_state.sources.values():
                if source.volume_link_id:
                    pv = self._find_pv_by_id(source.volume_link_id)
                    if pv:
                        # 1. Update Transform (Global)
                        global_pos, global_rot_rad = self._calculate_global_transform(pv)
                        
                        # Check if it actually changed to avoid unnecessary history spam? 
                        # (Actually, we are in a batch update, so we just append to the patch).
                        
                        source.position = {
                            'x': str(global_pos['x']), 'y': str(global_pos['y']), 'z': str(global_pos['z'])
                        }
                        source.rotation = {
                            'x': str(global_rot_rad['x']), 'y': str(global_rot_rad['y']), 'z': str(global_rot_rad['z'])
                        }
                        
                        # 2. Update Shape Parameters
                        lv = self.current_geometry_state.logical_volumes.get(pv.volume_ref)
                        if lv:
                            solid = self.current_geometry_state.solids.get(lv.solid_ref)
                            if solid:
                                p = solid._evaluated_parameters
                                cmds = source.gps_commands
                            # SAFETY MARGIN: Confinement requires generated points to be strictly INSIDE.
                            # We reduce the source dimensions slightly to stand clear of the boundary.
                            MARGIN = 0.001 # mm
                            
                            if solid.type in ['box']:
                                    cmds['pos/shape'] = 'Box'
                                    cmds['pos/halfx'] = f"{max(0, p.get('x', 0)/2 - MARGIN)} mm"
                                    cmds['pos/halfy'] = f"{max(0, p.get('y', 0)/2 - MARGIN)} mm"
                                    cmds['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                            elif solid.type in ['tube', 'cylinder', 'tubs']:
                                    cmds['pos/shape'] = 'Cylinder'
                                    cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                                    cmds['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                            elif solid.type in ['sphere', 'orb']:
                                    cmds['pos/shape'] = 'Sphere'
                                    cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                            else:
                                    cmds['pos/shape'] = 'Sphere'
                                    cmds['pos/radius'] = '50 mm'

                        # Update evaluated position for scene
                        source._evaluated_position = global_pos
                        source._evaluated_rotation = global_rot_rad
                        
                        sources_updated.append(source)

        except Exception as e:
            return False, None
        
        # --- Return the patch data  ---
        # (For now, do not attempt to patch the scene, as one transformation may affect several PVs
        #  and this is not yet accounted for.)
        # scene_patch = {
        #     "updated_transforms": [
        #         {
        #             "id": pv.id, # Ensure we use the object's ID
        #             "position": pv._evaluated_position,
        #             "rotation": pv._evaluated_rotation,
        #             "scale": pv._evaluated_scale
        #         } for pv in updated_pv_objects
        #     ]
        # }

        # This part is for updating the local data model (AppState)
        project_state_patch = {
            "updated": {
                # We need to send the full PV object so the frontend can replace it
                "physical_volumes": {pv.id: pv.to_dict() for pv in updated_pv_objects},
                # Also send updated sources
                "sources": {s.id: s.to_dict() for s in sources_updated}
            }
        }
        
        # If everything succeeded, capture the final state and return
        self._capture_history_state(f"Batch update to {len(updated_pv_objects)} PVs")
        return True, project_state_patch

    def add_assembly(self, name_suggestion, placements_data):
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.assemblies)
        new_assembly = Assembly(name)
        
        # Convert placement dicts into PhysicalVolumePlacement objects
        placements = [PhysicalVolumePlacement.from_dict(p_data) for p_data in placements_data]
        new_assembly.placements = placements
        
        self.current_geometry_state.add_assembly(new_assembly)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added assembly {name}")

        return new_assembly.to_dict(), None

    def update_assembly(self, assembly_name, new_placements_data):
        if not self.current_geometry_state:
            return False, "No project loaded"
        
        target_assembly = self.current_geometry_state.assemblies.get(assembly_name)
        if not target_assembly:
            return False, f"Assembly '{assembly_name}' not found."
            
        # Convert dicts to objects
        new_placements = [PhysicalVolumePlacement.from_dict(p_data) for p_data in new_placements_data]
        target_assembly.placements = new_placements

        success, error_msg = self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated assembly {assembly_name}")

        return success, error_msg
    
    def add_particle_source(self, name_suggestion, gps_commands, position, rotation, activity=1.0, confine_to_pv=None):
        if not self.current_geometry_state:
            return None, "No project loaded"

        if confine_to_pv == "":
            confine_to_pv = None

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.sources)
        new_source = ParticleSource(name, gps_commands, position, rotation, activity=activity, confine_to_pv=confine_to_pv)
        self.current_geometry_state.add_source(new_source)
        self.recalculate_geometry_state()
        self._capture_history_state(f"Added particle source {name}")
        return new_source.to_dict(), None

    def update_source_transform(self, source_id, new_position, new_rotation):
        """Updates just the position of a source."""
        if not self.current_geometry_state:
            return False, "No project loaded"

        source_to_update = None
        for source in self.current_geometry_state.sources.values():
            if source.id == source_id:
                source_to_update = source
                break

        if not source_to_update:
            return False, f"Source with ID '{source_id}' not found."

        if new_position is not None:
            # The new position from the gizmo is already evaluated (floats)
            # We need to store it as strings in the 'raw' position dict
            source_to_update.position = {k: str(v) for k, v in new_position.items()}

        if new_rotation is not None:
            source_to_update.rotation = {k: str(v) for k, v in new_rotation.items()}

        self.recalculate_geometry_state()
        self._capture_history_state(f"Transformed source {source_to_update.name}")
        return True, None
    
    def delete_objects_batch(self, objects_to_delete):
        """
        Deletes a list of objects in a single transaction, after checking all dependencies first.
        objects_to_delete: A list of dictionaries, e.g., [{"type": "solid", "id": "my_box"}, ...]
        """
        if not self.current_geometry_state:
            return False, "No project loaded."
        
        # --- Do not allow deletion of world PV or LV ---
        world_lv = self.current_geometry_state.logical_volumes[self.current_geometry_state.world_volume_ref]
        for item in objects_to_delete:

            print(f"Deleting item {item} for world LV {world_lv}")
    
            # Prevent deletion of the designated World Logical Volume.
            if item.get('type') == 'logical_volume' and item.get('name') == world_lv.name:
                return False, f"Cannot delete the World Logical Volume ('{world_lv.name}'). To start over, use 'File -> New Project'."
            
            # Also prevent deletion of the World's physical placement (though it's not directly selectable yet).
            # This is good future-proofing.
            if item.get('type') == 'physical_volume':
                pv = self._find_pv_by_id(item.get('id'))
                if pv and pv.volume_ref == world_lv.name:
                     return False, f"Cannot delete the world volume's placement."
        
        # --- Pre-deletion Validation Phase ---
        all_dependencies = {}
        for item in objects_to_delete:
            obj_type = item.get('type')
            obj_id = item.get('id')

            # --- SKIP DEPENDENCY CHECK FOR SOURCES ---
            if obj_type == 'particle_source':
                continue
            
            # Find dependencies, but exclude dependencies that are also being deleted in this same batch.
            # This allows deleting an LV and the PV that contains it at the same time.
            dependencies = self._find_dependencies(obj_type, obj_id)
            
            # Filter out dependencies that are also scheduled for deletion in this batch.
            item_ids_being_deleted = {i.get('id') for i in objects_to_delete if i.get('id')}
            filtered_deps = []
            for dep_string in dependencies:
                is_also_being_deleted = False
                for del_id in item_ids_being_deleted:
                    # Create a regex to match the exact ID as a whole word,
                    # typically inside single quotes.
                    # Example: `f"'({re.escape(del_id)})'"` matches "'Box'" but not "'logBox'".
                    # We add word boundaries (\b) for extra safety.
                    pattern = r"\b" + re.escape(del_id) + r"\b"
                    if re.search(pattern, dep_string):
                        is_also_being_deleted = True
                        break # Found a match, no need to check other del_ids for this dependency
                
                if not is_also_being_deleted:
                    filtered_deps.append(dep_string)

            if filtered_deps:
                all_dependencies[f"{obj_type} '{obj_id}'"] = filtered_deps

        if all_dependencies:
            # Format a comprehensive error message
            error_msg = "Deletion failed. The following objects are still in use:\n"
            for obj, deps in all_dependencies.items():
                dep_list_str = "\n  - " + "\n  - ".join(deps)
                error_msg += f"\n• {obj} is used by:{dep_list_str}"
            return False, error_msg

        # --- Deletion Phase ---
        # If we passed validation, it's safe to delete everything.
        try:
            for item in objects_to_delete:
                # The internal _delete_single_object_no_checks is a new helper
                self._delete_single_object_no_checks(item['type'], item['id'])
        except Exception as e:
            # In case of an unexpected error, revert and report.
            # A more robust solution would be to restore from self._pre_transaction_state
            return False, str(e)
        
        # --- Finalization ---
        # No full geometry recalculation needed here for a simple delete.
        self._capture_history_state(f"Deleted {len(objects_to_delete)} objects")

        # --- Build the patch object for the response ---
        project_state_patch = {
            "deleted": {
                # Initialize with all types that can be deleted
                "solids": [], "logical_volumes": [], "physical_volumes": [],
                "materials": [], "elements": [], "isotopes": [], "defines": [],
                "assemblies": [], "optical_surfaces": [], "skin_surfaces": [], 
                "border_surfaces": [], "particle_sources": []
            }
        }
        for item in objects_to_delete:
            obj_type = item['type']
            obj_id = item['id']
            # Map frontend types to backend dictionary keys if they differ
            dict_key = ""
            if obj_type == "particle_source":
                dict_key = "particle_sources"
            elif obj_type == "assembly":
                dict_key = "assemblies"
            else:
                dict_key = f"{obj_type}s"
            if dict_key in project_state_patch["deleted"]:
                 project_state_patch["deleted"][dict_key].append(obj_id)

        # A deletion might affect the scene, so we should send a full scene update.
        scene_update = self.get_threejs_description()

        patch = {
            "project_state": project_state_patch,
            "scene_update": scene_update
        }
        
        return True, patch

    def _delete_single_object_no_checks(self, object_type, object_id):
        """
        Internal helper that performs the actual deletion from the state dictionaries.
        This function ASSUMES all dependency checks have already passed.
        """
        state = self.current_geometry_state
        deleted = False
        error_msg = None

        if object_type == "define":
            if object_id in state.defines:
                del state.defines[object_id]
                deleted = True
    
        elif object_type == "material":
            if object_id in state.materials:
                del state.materials[object_id]
                deleted = True
    
        elif object_type == "element":
            if object_id in state.elements:
                del state.elements[object_id]
                deleted = True
    
        elif object_type == "isotope":
            if object_id in state.isotopes:
                del state.isotopes[object_id]
                deleted = True
    
        elif object_type == "assembly":
            if object_id in state.assemblies:
                del state.assemblies[object_id]
                deleted = True
    
        elif object_type == "optical_surface":
            if object_id in state.optical_surfaces:
                del state.optical_surfaces[object_id]
                deleted = True
    
        elif object_type == "skin_surface":
            if object_id in state.skin_surfaces:
                del state.skin_surfaces[object_id]
                deleted = True
    
        elif object_type == "border_surface":
            if object_id in state.border_surfaces:
                del state.border_surfaces[object_id]
                deleted = True
    
        elif object_type == "solid":
            if object_id in state.solids:
                del state.solids[object_id]
                deleted = True
        
        elif object_type == "logical_volume":
            if object_id in state.logical_volumes:
                if state.world_volume_ref == object_id:
                    error_msg = "Cannot delete the world volume."
                else:
                    # Delete the LV itself
                    del state.logical_volumes[object_id]
                    
                    # Now, remove any placements that REFER to this deleted LV
                    for lv in state.logical_volumes.values():
                        if lv.content_type == 'physvol':
                            lv.content = [pv for pv in lv.content if pv.volume_ref != object_id]
                        elif lv.content and hasattr(lv.content, 'volume_ref') and lv.content.volume_ref == object_id:
                            # If a procedural volume was replicating the deleted LV, reset it.
                            # A more advanced implementation might delete the procedural LV entirely.
                            lv.content_type = 'physvol'
                            lv.content = []
                    deleted = True
        
        elif object_type == "physical_volume":
            # Iterate through all LVs and check their 'content' list for the PV to delete
            found_and_deleted = False
            for lv in state.logical_volumes.values():
                if lv.content_type == 'physvol':
                    original_len = len(lv.content)
                    # Filter the list, keeping only PVs that DON'T match the ID
                    lv.content = [pv for pv in lv.content if pv.id != object_id]
                    if len(lv.content) < original_len:
                        found_and_deleted = True
                        break # Found and deleted, no need to search further
            
            if found_and_deleted:
                deleted = True
                # Clean up any sources that were linked to this PV
                for source in state.sources.values():
                    if source.volume_link_id == object_id:
                        source.volume_link_id = None
                        # We also clear the confinement name to prevent confusion, 
                        # as the specific instance binding is gone.
                        source.confine_to_pv = None
            else:
                error_msg = "Physical Volume not found."

        elif object_type == "particle_source":
            source_to_delete = None
            for name, source in state.sources.items():
                if source.id == object_id:
                    source_to_delete = name
                    break
            if source_to_delete:
                del state.sources[source_to_delete]
                # If the deleted source was the active one, clear the active ID
                if object_id in state.active_source_ids:
                    state.active_source_ids.remove(object_id)
                deleted = True
        
        return deleted, error_msg if error_msg else f"Object {object_type} '{object_id}' not found or cannot be deleted."

    def _find_dependencies(self, object_type, object_id):
        """
        Finds all objects that reference a given object.
        Returns a list of strings describing the dependencies.
        """
        dependencies = []
        state = self.current_geometry_state
        if object_type == 'solid':
            # Check Logical Volumes
            for lv in state.logical_volumes.values():
                if lv.solid_ref == object_id:
                    dependencies.append(f"Logical Volume '{lv.name}'")
            # Check Boolean Solids
            for solid in state.solids.values():
                if solid.type == 'boolean':
                    for item in solid.raw_parameters.get('recipe', []):
                        if item.get('solid_ref') == object_id:
                            dependencies.append(f"Boolean Solid '{solid.name}'")
                            break # Only need to report once per solid

        elif object_type == 'material':
            # Check Logical Volumes
            for lv in state.logical_volumes.values():
                if lv.material_ref == object_id:
                    dependencies.append(f"Logical Volume '{lv.name}'")

        elif object_type == 'define':
            search_str = object_id
            
            # --- 1. Check for usage in other Defines ---
            for define_obj in state.defines.values():
                if define_obj.name == search_str: continue # Don't check against self
                
                # Check raw_expression, which can be a string or a dict
                raw_expr = define_obj.raw_expression
                if isinstance(raw_expr, str):
                    if re.search(r'\b' + re.escape(search_str) + r'\b', raw_expr):
                        dependencies.append(f"Define '{define_obj.name}'")
                elif isinstance(raw_expr, dict):
                    for val in raw_expr.values():
                        if isinstance(val, str) and re.search(r'\b' + re.escape(search_str) + r'\b', val):
                            dependencies.append(f"Define '{define_obj.name}'")
                            break # Found in this dict, no need to check other keys

            # --- 2. Check for usage in Solids ---
            for solid in state.solids.values():
                is_found_in_solid = False
                for key, val in solid.raw_parameters.items():
                    if isinstance(val, str) and re.search(r'\b' + re.escape(search_str) + r'\b', val):
                        dependencies.append(f"Solid '{solid.name}' (parameter '{key}')")
                        is_found_in_solid = True
                        break # Only report once per solid
                    elif isinstance(val, dict): # For nested structures like boolean transforms
                        for sub_val in val.values():
                            if isinstance(sub_val, str) and re.search(r'\b' + re.escape(search_str) + r'\b', sub_val):
                                dependencies.append(f"Solid '{solid.name}' (parameter '{key}')")
                                is_found_in_solid = True
                                break
                    if is_found_in_solid: break
                if is_found_in_solid: continue
                # Also check boolean recipes
                if solid.type == 'boolean':
                    for item in solid.raw_parameters.get('recipe', []):
                        transform = item.get('transform', {})
                        if transform:
                            pos = transform.get('position', {})
                            rot = transform.get('rotation', {})
                            if (isinstance(pos, str) and pos == search_str) or \
                               (isinstance(rot, str) and rot == search_str):
                                dependencies.append(f"Solid '{solid.name}' (transform reference)")
                                break

            # --- 3. Check for usage in all Placements (Standard, Assembly, Procedural) ---
            all_lvs = list(state.logical_volumes.values())
            all_asms = list(state.assemblies.values())
            
            # Standard LV placements
            for lv in all_lvs:
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.position == search_str: dependencies.append(f"Placement '{pv.name}' (position)")
                        if pv.rotation == search_str: dependencies.append(f"Placement '{pv.name}' (rotation)")
                        if pv.scale == search_str: dependencies.append(f"Placement '{pv.name}' (scale)")
            
            # Assembly placements
            for asm in all_asms:
                for pv in asm.placements:
                    if pv.position == search_str: dependencies.append(f"Placement '{pv.name}' (position)")
                    if pv.rotation == search_str: dependencies.append(f"Placement '{pv.name}' (rotation)")
                    if pv.scale == search_str: dependencies.append(f"Placement '{pv.name}' (scale)")

            # --- 4. Check for usage in Procedural Volume parameters ---
            for lv in all_lvs:
                if lv.content_type in ['replica', 'division', 'parameterised']:
                    proc_obj = lv.content
                    # Check number/ncopies, width, offset
                    for attr in ['number', 'width', 'offset', 'ncopies']:
                        if hasattr(proc_obj, attr):
                            attr_val = getattr(proc_obj, attr)
                            if isinstance(attr_val, str) and re.search(r'\b' + re.escape(search_str) + r'\b', attr_val):
                                dependencies.append(f"Procedural Volume in '{lv.name}' (parameter '{attr}')")
                                break
                    # Check parameterised volume dimensions
                    if hasattr(proc_obj, 'parameters'):
                        for param_set in proc_obj.parameters:
                            def _dimension_contains_search(value):
                                if isinstance(value, str):
                                    return re.search(r'\b' + re.escape(search_str) + r'\b', value) is not None
                                if isinstance(value, dict):
                                    return any(_dimension_contains_search(item) for item in value.values())
                                if isinstance(value, list):
                                    return any(_dimension_contains_search(item) for item in value)
                                return False

                            if any(_dimension_contains_search(dim_val) for dim_val in param_set.dimensions.values()):
                                dependencies.append(f"Parameterised Volume in '{lv.name}' (dimensions)")
                                break
                            if param_set.position == search_str:
                                dependencies.append(f"Parameterised Volume in '{lv.name}' (position ref)")
                            if param_set.rotation == search_str:
                                dependencies.append(f"Parameterised Volume in '{lv.name}' (rotation ref)")

            # --- 5. Check for usage in Optical/Skin/Border Surfaces ---
            for surf in state.optical_surfaces.values():
                for key, val in surf.properties.items():
                    if val == search_str:
                        dependencies.append(f"Optical Surface '{surf.name}' (property '{key}')")

        elif object_type == 'logical_volume':
            # Check for placements in other LVs
            for lv in state.logical_volumes.values():
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.volume_ref == object_id:
                            dependencies.append(f"Placement '{pv.name}' in Logical Volume '{lv.name}'")
            # Check for placements in Assemblies
            for asm in state.assemblies.values():
                for pv in asm.placements:
                    if pv.volume_ref == object_id:
                        dependencies.append(f"Placement '{pv.name}' in Assembly '{asm.name}'")
            # Check for skin surfaces
            for skin in state.skin_surfaces.values():
                if skin.volume_ref == object_id:
                    dependencies.append(f"Skin Surface '{skin.name}'")

        elif object_type == 'assembly':
            # Check for placements in other LVs
            for lv in state.logical_volumes.values():
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.volume_ref == object_id:
                            dependencies.append(f"Placement '{pv.name}' in Logical Volume '{lv.name}'")
            # Check for placements in other Assemblies (nested assemblies)
            for asm in state.assemblies.values():
                for pv in asm.placements:
                    if pv.volume_ref == object_id:
                        dependencies.append(f"Placement '{pv.name}' in Assembly '{asm.name}'")

        # Add more checks for elements, isotopes, optical_surfaces etc. as needed.
        return sorted(list(set(dependencies)))

    def merge_from_state(self, incoming_state: GeometryState):
        """
        Merges defines, materials, solids, and LVs from an incoming state
        into the current project, handling name conflicts by renaming.
        """
        if not self.current_geometry_state:
            self.current_geometry_state = incoming_state
            # Even if it's a fresh state, it might have placements to add
            if hasattr(incoming_state, 'placements_to_add'):
                for pv_to_add in incoming_state.placements_to_add:
                    parent_lv = self.current_geometry_state.logical_volumes.get(pv_to_add.parent_lv_name)
                    if parent_lv:
                        parent_lv.add_child(pv_to_add)
                    else:
                        print(f"Warning: Could not find parent LV '{pv_to_add.parent_lv_name}' for initial placement.")
            return True, None

        rename_map = {} # Tracks old_name -> new_name

        # --- Merge Defines ---
        for name, define in incoming_state.defines.items():
            new_name = self._generate_unique_name(name, self.current_geometry_state.defines)
            if new_name != name:
                rename_map[name] = new_name
            define.name = new_name
            self.current_geometry_state.add_define(define)

        # --- Merge Materials ---
        for name, material in incoming_state.materials.items():
            # Update component references if their names were changed
            if material.components:
                for comp in material.components:
                    if comp['ref'] in rename_map:
                        comp['ref'] = rename_map[comp['ref']]
            
            new_name = self._generate_unique_name(name, self.current_geometry_state.materials)
            if new_name != name:
                rename_map[name] = new_name
            material.name = new_name
            self.current_geometry_state.add_material(material)

        # --- Merge Solids ---
        for name, solid in incoming_state.solids.items():
            # Update solid references within booleans
            if solid.type in ['boolean', 'union', 'subtraction', 'intersection']:
                if solid.type == 'boolean': # New virtual boolean
                    for item in solid.raw_parameters.get('recipe', []):
                        if item['solid_ref'] in rename_map:
                            item['solid_ref'] = rename_map[item['solid_ref']]
                else: # Old style boolean
                    if solid.raw_parameters['first_ref'] in rename_map:
                        solid.raw_parameters['first_ref'] = rename_map[solid.raw_parameters['first_ref']]
                    if solid.raw_parameters['second_ref'] in rename_map:
                        solid.raw_parameters['second_ref'] = rename_map[solid.raw_parameters['second_ref']]

            new_name = self._generate_unique_name(name, self.current_geometry_state.solids)
            if new_name != name:
                rename_map[name] = new_name
            solid.name = new_name
            self.current_geometry_state.add_solid(solid)

        # --- Merge Logical Volumes ---
        processed_lvs = []
        extra_placements = []
        for name, lv in incoming_state.logical_volumes.items():
            # Ignore the incoming world volume BUT capture its placements
            if name == incoming_state.world_volume_ref:
                # Map old world to current world so children can find their new parent
                rename_map[name] = self.current_geometry_state.world_volume_ref
                
                # Extract content to be added as placements
                if lv.content_type == 'physvol' and isinstance(lv.content, list):
                     for pv in lv.content:
                         # Clone via serialization to be safe
                         pv_clone = PhysicalVolumePlacement.from_dict(pv.to_dict())
                         # Explicitly re-parent them to the current world volume
                         pv_clone.parent_lv_name = self.current_geometry_state.world_volume_ref
                         extra_placements.append(pv_clone)
                continue

            # Update references within this LV
            if lv.solid_ref in rename_map: lv.solid_ref = rename_map[lv.solid_ref]
            if lv.material_ref in rename_map: lv.material_ref = rename_map[lv.material_ref]
            
            # Note: We are preserving internal placements (sub-assemblies).
            # We will fix up their references in a second pass.

            new_name = self._generate_unique_name(name, self.current_geometry_state.logical_volumes)
            if new_name != name:
                rename_map[name] = new_name
            lv.name = new_name
            
            self.current_geometry_state.add_logical_volume(lv)
            processed_lvs.append(lv)

        # --- Post-Process LV Content (Fix references in children) ---
        for lv in processed_lvs:
            if lv.content_type == 'physvol' and isinstance(lv.content, list):
                for pv in lv.content:
                    # Update reference to the child volume (if it was renamed)
                    if pv.volume_ref in rename_map:
                        pv.volume_ref = rename_map[pv.volume_ref]
                    
                    # Update reference to the parent volume (this LV, which might have been renamed)
                    pv.parent_lv_name = lv.name 
                    
                    # Update defines in positioning
                    if isinstance(pv.position, str) and pv.position in rename_map:
                         pv.position = rename_map[pv.position]
                    if isinstance(pv.rotation, str) and pv.rotation in rename_map:
                         pv.rotation = rename_map[pv.rotation]
        
        # --- Merge Assemblies ---
        for name, assembly in incoming_state.assemblies.items():
            # Update all references within the assembly's placements
            for pv in assembly.placements:
                if pv.volume_ref in rename_map:
                    pv.volume_ref = rename_map[pv.volume_ref]
                if isinstance(pv.position, str) and pv.position in rename_map:
                    pv.position = rename_map[pv.position]
                if isinstance(pv.rotation, str) and pv.rotation in rename_map:
                    pv.rotation = rename_map[pv.rotation]
            
            new_name = self._generate_unique_name(name, self.current_geometry_state.assemblies)
            if new_name != name:
                rename_map[name] = new_name
            assembly.name = new_name
            self.current_geometry_state.add_assembly(assembly)

        # --- Merge Sources ---
        for name, source in incoming_state.sources.items():
            old_id = source.id
            
            # Generate new unique name
            new_name = self._generate_unique_name(name, self.current_geometry_state.sources)
            if new_name != name:
                rename_map[name] = new_name
            source.name = new_name
            
            # Generate new ID to avoid collisions (especially on re-import)
            import uuid
            new_id = str(uuid.uuid4())
            source.id = new_id
            
            self.current_geometry_state.add_source(source)
            
            # If this source was active in the incoming state, activate it in the current state
            if old_id in incoming_state.active_source_ids:
                self.current_geometry_state.active_source_ids.append(new_id)

        incoming_cad_imports = getattr(incoming_state, 'cad_imports', None)
        if incoming_cad_imports:
            if not isinstance(getattr(self.current_geometry_state, 'cad_imports', None), list):
                self.current_geometry_state.cad_imports = []
            for cad_import in incoming_cad_imports:
                if isinstance(cad_import, dict):
                    self.current_geometry_state.cad_imports.append(deepcopy(cad_import))

        # --- Process and Add Placements ---
        # Combine explicitly requested placements with those extracted from the incoming world
        all_placements_to_add = (getattr(incoming_state, 'placements_to_add', []) or []) + extra_placements
        
        if all_placements_to_add:
            for pv_to_add in all_placements_to_add:
                # 1. Update any renamed references within the placement object
                if pv_to_add.parent_lv_name in rename_map:
                    pv_to_add.parent_lv_name = rename_map[pv_to_add.parent_lv_name]
                
                if pv_to_add.volume_ref in rename_map:
                    pv_to_add.volume_ref = rename_map[pv_to_add.volume_ref]
                
                if isinstance(pv_to_add.position, str) and pv_to_add.position in rename_map:
                    pv_to_add.position = rename_map[pv_to_add.position]
                
                if isinstance(pv_to_add.rotation, str) and pv_to_add.rotation in rename_map:
                    pv_to_add.rotation = rename_map[pv_to_add.rotation]

                # 2. Find the parent LV in the *main* project state
                parent_lv = self.current_geometry_state.logical_volumes.get(pv_to_add.parent_lv_name)

                if parent_lv:
                    if parent_lv.content_type == 'physvol':
                        # Generate a unique name for the placement within its new parent
                        existing_names = {pv.name for pv in parent_lv.content}
                        base_name = pv_to_add.name
                        i = 1
                        while pv_to_add.name in existing_names:
                            pv_to_add.name = f"{base_name}_{i}"
                            i += 1

                        parent_lv.add_child(pv_to_add)
                    else:
                        print(f"Warning: Cannot add placement '{pv_to_add.name}'. Parent LV '{parent_lv.name}' is procedural.")
                else:
                    print(f"Warning: Could not find parent LV '{pv_to_add.parent_lv_name}' for imported placement '{pv_to_add.name}'. Skipping.")
        
        # --- Auto-Grouping Logic ---
        if hasattr(incoming_state, 'grouping_name'):
             grouping_name = incoming_state.grouping_name
             
             # Group Solids
             new_solid_names = [s.name for s in incoming_state.solids.values()]
             if new_solid_names:
                 self.create_group('solid', f"{grouping_name}_solids")
                 self.move_items_to_group('solid', new_solid_names, f"{grouping_name}_solids")

             # Group Logical Volumes
             new_lv_names = [lv.name for lv in incoming_state.logical_volumes.values()]
             if new_lv_names:
                 self.create_group('logical_volume', f"{grouping_name}_lvs")
                 self.move_items_to_group('logical_volume', new_lv_names, f"{grouping_name}_lvs")

             # Group Assembly (if created)
             new_asm_names = [asm.name for asm in incoming_state.assemblies.values()]
             if new_asm_names:
                 self.create_group('assembly', f"{grouping_name}_assemblies")
                 self.move_items_to_group('assembly', new_asm_names, f"{grouping_name}_assemblies")

        # Recalculate the state
        success, error_msg = self.recalculate_geometry_state()

        # RE-SYNC ALL BOUND SOURCES (Crucial for imported parts)
        # Imported bound sources may have outdated shape parameters or positions relative to the new World.
        for source in self.current_geometry_state.sources.values():
            if source.volume_link_id:
                pv = self._find_pv_by_id(source.volume_link_id)
                if pv:
                    # 1. Update Transform (Global)
                    global_pos, global_rot_rad = self._calculate_global_transform(pv)
                    
                    source.position = {
                        'x': str(global_pos['x']), 'y': str(global_pos['y']), 'z': str(global_pos['z'])
                    }
                    source.rotation = {
                        'x': str(global_rot_rad['x']), 'y': str(global_rot_rad['y']), 'z': str(global_rot_rad['z'])
                    }
                    
                    # 2. Update Shape Parameters
                    lv = self.current_geometry_state.logical_volumes.get(pv.volume_ref)
                    if lv:
                        solid = self.current_geometry_state.solids.get(lv.solid_ref)
                        if solid:
                            p = solid._evaluated_parameters
                            cmds = source.gps_commands
                            cmds['pos/type'] = 'Volume'
                            
                            # SAFETY MARGIN: Confinement requires generated points to be strictly INSIDE.
                            # We reduce the source dimensions slightly to stand clear of the boundary.
                            MARGIN = 0.001 # mm
                            
                            if solid.type in ['box']:
                                cmds['pos/shape'] = 'Box'
                                cmds['pos/halfx'] = f"{max(0, p.get('x', 0)/2 - MARGIN)} mm"
                                cmds['pos/halfy'] = f"{max(0, p.get('y', 0)/2 - MARGIN)} mm"
                                cmds['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                            elif solid.type in ['tube', 'cylinder', 'tubs']:
                                cmds['pos/shape'] = 'Cylinder'
                                cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                                cmds['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                            elif solid.type in ['sphere', 'orb']:
                                cmds['pos/shape'] = 'Sphere'
                                cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                            else:
                                cmds['pos/shape'] = 'Sphere'
                                cmds['pos/radius'] = '50 mm'

                    source._evaluated_position = global_pos
                    source._evaluated_rotation = global_rot_rad

        # Capture the new state
        self._capture_history_state(f"State merge")

        return success, error_msg

    def _evaluate_vector_expression(self, expr_data, default_dict=None):
        """
        Evaluates a vector-like expression which can be a define reference (string)
        or a dictionary of expression strings.
        """
        if default_dict is None:
            default_dict = {'x': 0.0, 'y': 0.0, 'z': 0.0}

        if isinstance(expr_data, str):
            # It's a reference to a define
            success, value = self.expression_evaluator.evaluate(expr_data)
            if success and isinstance(value, dict):
                # Ensure all keys exist in the resolved dict
                return {k: float(value.get(k, default_dict.get(k, 0))) for k in ['x', 'y', 'z']}
            else:
                raise ValueError(f"Define '{expr_data}' did not resolve to a valid dictionary.")
        elif isinstance(expr_data, dict):
            evaluated_dict = {}
            for axis in ['x', 'y', 'z']:
                raw_expr = expr_data.get(axis, default_dict.get(axis, 0))
                success, value = self.expression_evaluator.evaluate(str(raw_expr))
                if success:
                    evaluated_dict[axis] = value
                else:
                    raise ValueError(f"Failed to evaluate expression '{raw_expr}' for axis '{axis}'.")
            return evaluated_dict
        else:
            return default_dict
        
    def create_detector_ring(self, parent_lv_name, lv_to_place_ref, ring_name,
                             num_detectors, radius, center, orientation,
                             point_to_center, inward_axis,
                             num_rings=1, ring_spacing=0.0):
        """
        Creates a ring or cylinder of individual physical volumes.
        This method calculates the absolute world transform for each PV.
        """
        if not self.current_geometry_state:
            return None, "No project loaded"

        # --- AUTO-CLEANUP: If a ring with this name already exists, delete it first ---
        existing_pvs = []
        for lv in self.current_geometry_state.logical_volumes.values():
            if lv.content_type == 'physvol':
                for pv in lv.content:
                    if pv.name == ring_name:
                        existing_pvs.append({"type": "physical_volume", "id": pv.id})
        
        if existing_pvs:
            print(f"create_detector_ring: Automatically cleaning up {len(existing_pvs)} existing instances of '{ring_name}'.")
            self.delete_objects_batch(existing_pvs)

        try:
            # --- Evaluate all expression-capable arguments ---
            success_radius, evaluated_radius = self.expression_evaluator.evaluate(str(radius))
            if not success_radius: raise ValueError(f"Could not evaluate radius expression: '{radius}'")

            success_num_det, evaluated_num_detectors = self.expression_evaluator.evaluate(str(num_detectors))
            if not success_num_det: raise ValueError(f"Could not evaluate num_detectors: '{num_detectors}'")
            evaluated_num_detectors = int(evaluated_num_detectors)

            success_num_rings, evaluated_num_rings = self.expression_evaluator.evaluate(str(num_rings))
            if not success_num_rings: raise ValueError(f"Could not evaluate num_rings: '{num_rings}'")
            evaluated_num_rings = int(evaluated_num_rings)

            success_spacing, evaluated_ring_spacing = self.expression_evaluator.evaluate(str(ring_spacing))
            if not success_spacing: raise ValueError(f"Could not evaluate ring_spacing: '{ring_spacing}'")

            evaluated_center = self._evaluate_vector_expression(center, {'x': 0.0, 'y': 0.0, 'z': 0.0})
            evaluated_orientation = self._evaluate_vector_expression(orientation, {'x': 0.0, 'y': 0.0, 'z': 0.0})

        except (ValueError, TypeError) as e:
            return None, f"Error evaluating tool arguments: {e}"

        state = self.current_geometry_state
        parent_lv = state.logical_volumes.get(parent_lv_name)
        if not parent_lv:
            return None, f"Parent Logical Volume '{parent_lv_name}' not found."
        if parent_lv.content_type != 'physvol':
            return None, f"Parent LV '{parent_lv_name}' is procedural and cannot contain new placements."

        # --- Main Transformation for the entire array ---
        # We use scipy's Rotation which uses intrinsic ZYX order for 'zyx'
        # This matches our convention for the evaluated values.
        global_rotation = R.from_euler('zyx', [evaluated_orientation['z'], evaluated_orientation['y'], evaluated_orientation['x']])
        global_center = np.array([evaluated_center['x'], evaluated_center['y'], evaluated_center['z']])

        total_height = (evaluated_num_rings - 1) * evaluated_ring_spacing
        start_z = -total_height / 2.0

        copy_number_counter = self._get_next_copy_number(parent_lv)

        placements_to_add = []

        for j in range(evaluated_num_rings):
            z_pos = start_z + j * evaluated_ring_spacing
            for i in range(evaluated_num_detectors):
                angle = 2 * math.pi * i / evaluated_num_detectors

                # 1. Position of the crystal in the local XY plane of the ring
                local_position = np.array([evaluated_radius * math.cos(angle),
                                           evaluated_radius * math.sin(angle),
                                           z_pos])

                # 2. Calculate the "look-at" rotation to point the crystal to the center, without roll
                if point_to_center:
                    # The vector from the crystal to the ring axis
                    z_new = -np.array([local_position[0], local_position[1], 0])
                    # Normalize, with a safe guard for the center crystal
                    norm = np.linalg.norm(z_new)
                    if norm > 1e-9:
                        z_new /= norm
                    else:
                        z_new = np.array([0, -1, 0]) # Fallback for a crystal at the origin

                    # The global "up" vector for the ring is its local Z-axis
                    up_vector = np.array([0, 0, 1])

                    # Create an orthonormal basis
                    x_new = np.cross(up_vector, z_new)
                    x_new /= np.linalg.norm(x_new)
                    y_new = np.cross(z_new, x_new)

                    # This matrix transforms from standard axes to the "look-at" axes
                    look_at_matrix = np.column_stack([x_new, y_new, z_new])
                    R_lookat = R.from_matrix(look_at_matrix)
                else:
                    R_lookat = R.identity()

                # 3. Calculate pre-rotation to align the desired crystal axis
                source_vector_map = {
                    '+x': R.from_euler('y', -90, degrees=True),
                    '-x': R.from_euler('y', 90, degrees=True),
                    '+y': R.from_euler('x', 90, degrees=True),
                    '-y': R.from_euler('x', -90, degrees=True),
                    '+z': R.identity(),
                    '-z': R.from_euler('y', 180, degrees=True)
                }
                R_pre_rot = source_vector_map.get(inward_axis, R.identity())

                # 4. Combine rotations: global orientation -> local look-at -> pre-rotation
                final_rotation = global_rotation * R_lookat * R_pre_rot

                # 5. Transform local position to world position
                final_position = global_rotation.apply(local_position) + global_center

                # 6. Convert final rotation back to our negated ZYX Euler angles for storage
                final_euler_rad = final_rotation.as_euler('zyx', degrees=False)
                final_rotation_dict = {
                    'x': str(-final_euler_rad[2]),
                    'y': str(-final_euler_rad[1]),
                    'z': str(-final_euler_rad[0])
                }

                # Create the PhysicalVolumePlacement object for this detector
                pv = PhysicalVolumePlacement(
                    name=ring_name,  # All PVs share the same base name
                    volume_ref=lv_to_place_ref,
                    parent_lv_name=parent_lv_name,
                    copy_number_expr=str(copy_number_counter),
                    position_val_or_ref={'x': str(final_position[0]), 'y': str(final_position[1]), 'z': str(final_position[2])},
                    rotation_val_or_ref=final_rotation_dict
                )
                placements_to_add.append(pv)
                copy_number_counter += 1

        # Add all newly created placements to the parent logical volume
        parent_lv.content.extend(placements_to_add)

        self._capture_history_state(f"Created detector array '{ring_name}'")
        self.recalculate_geometry_state()

        # Returning the last created PV as a representative object, or None
        return placements_to_add[-1].to_dict() if placements_to_add else None, None
    
    def process_ai_response(self, ai_data: dict):
        """
        Processes a structured dictionary from the AI, creating new objects
        and applying updates like placements.
        """
        if not self.current_geometry_state:
            return False, "No project loaded."

        # print("RECEIVED AI DATA")
        # print(ai_data)

        # *** Recursively convert all rotation dictionaries ***
        self._recursively_convert_rotations(ai_data)

        # --- 1. Handle the 'creates' block ---
        # This block defines new, standalone items. We can merge them all at once.
        creation_data = ai_data.get("creates", {})
        if creation_data:
            temp_state = GeometryState.from_dict(creation_data)
            success, error_msg = self.merge_from_state(temp_state)
            if not success:
                return False, f"Failed to merge AI-defined objects: {error_msg}"
        
        # --- 2. Handle the 'updates' block ---
        # This block modifies existing objects, like placing volumes inside another.
        updates = ai_data.get("updates", [])
        if not isinstance(updates, list):
            return False, "AI response had an invalid 'updates' format (must be a list)."

        for update_task in updates:
            try:
                obj_type = update_task['object_type']
                obj_name = update_task['object_name']
                action = update_task['action']
                data = update_task['data']

                if obj_type == "logical_volume" and action == "append_physvol":
                    parent_lv = self.current_geometry_state.logical_volumes.get(obj_name)
                    if not parent_lv:
                        return False, f"Parent logical volume '{obj_name}' not found for placement."
                    
                    if parent_lv.content_type != 'physvol':
                         return False, f"Cannot add a physical volume to '{obj_name}' because it is procedurally defined as a '{parent_lv.content_type}'."

                    # The 'data' dictionary is a complete PhysicalVolumePlacement dictionary
                    new_pv = PhysicalVolumePlacement.from_dict(data)
                    parent_lv.add_child(new_pv)

                else:
                    # Placeholder for future actions like "update_property", "delete_item", etc.
                    print(f"Warning: AI requested unknown action '{action}' on '{obj_type}'. Ignoring.")

            except KeyError as e:
                return False, f"AI update data is missing a required key: {e}"
            except Exception as e:
                return False, f"An error occurred during AI update processing: {e}"

        # --- Handle tool calls ---
        tool_calls = ai_data.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            return False, "AI response 'tool_calls' must be a list."

        for call in tool_calls:
            tool_name = call.get("tool_name")
            arguments = call.get("arguments", {})

            if tool_name == "create_detector_ring":
                try:
                    # The **arguments syntax unpacks the dictionary into keyword arguments
                    _, error_msg = self.create_detector_ring(**arguments)
                    if error_msg:
                        return False, f"Error executing tool '{tool_name}': {error_msg}"
                except TypeError as e:
                    return False, f"Mismatched arguments for tool '{tool_name}': {e}"
                except Exception as e:
                    return False, f"An unexpected error occurred during tool execution: {e}"
            else:
                return False, f"Unknown tool requested by AI: '{tool_name}'"
            
        # --- 3. Recalculate everything once at the end ---
        success, error_msg = self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Incorporated AI response")

        return success, error_msg
    
    def _convert_ai_rotation_to_g4(self, rotation_dict):
        """
        Converts a standard intrinsic ZYX Euler rotation dictionary from the AI
        to the Geant4 extrinsic XYZ Euler rotation with negation.
        Geant4 extrinsic XYZ is equivalent to intrinsic ZYX with negated angles.
        """
        print(f"CONVERTING rotation",rotation_dict)
        if not isinstance(rotation_dict, dict):
            # This is likely a reference to a <define>, leave it as is.
            return rotation_dict

        # We are converting from what Three.js/graphics use (intrinsic ZYX)
        # to what Geant4 GDML uses (extrinsic XYZ). This happens to be
        # a simple negation of each angle.
        converted_rotation = {}
        for axis in ['x', 'y', 'z']:
            original_expr = rotation_dict.get(axis, '0').strip()
            # If the expression is just '0' or '0.0', no need to wrap it
            if original_expr in ['0', '0.0']:
                converted_rotation[axis] = "0"
            else:
                # Wrap the original expression in parentheses and prepend a minus sign
                converted_rotation[axis] = f"-({original_expr})"
        return converted_rotation
    
    def _recursively_convert_rotations(self, data):
        """Recursively traverses a dictionary or list to find and convert 'rotation' dictionaries."""
        if isinstance(data, dict):
            for key, value in data.items():
                if key == 'rotation' and value is not None:
                    data[key] = self._convert_ai_rotation_to_g4(value)
                else:
                    self._recursively_convert_rotations(value)
        elif isinstance(data, list):
            for item in data:
                self._recursively_convert_rotations(item)

    def import_step_with_options(self, step_file_stream, options):
        """
        Processes an uploaded STEP file using options, imports the geometry,
        and merges it into the current project.

        Returns:
            (success: bool, error_msg: Optional[str], import_report: Optional[dict])
        """
        # Save the stream to a temporary file to be read by the STEP parser
        with tempfile.NamedTemporaryFile(delete=False, suffix=".step") as temp_f:
            step_file_stream.save(temp_f.name)
            temp_path = temp_f.name
        
        try:
            target_import_id = _get_step_reimport_target_import_id(options)
            target_import_index = None
            target_import_record = None

            effective_options = deepcopy(options) if isinstance(options, dict) else {}
            if target_import_id:
                target_import_index, target_import_record = self._find_step_import_record(target_import_id)
                if target_import_record is None:
                    return False, f"STEP reimport target '{target_import_id}' was not found.", None

                prior_options = target_import_record.get('options', {})
                if isinstance(prior_options, dict):
                    if not effective_options.get('groupingName'):
                        effective_options['groupingName'] = prior_options.get('grouping_name', 'STEP_Import')
                    if not effective_options.get('placementMode'):
                        effective_options['placementMode'] = prior_options.get('placement_mode', 'assembly')
                    if not effective_options.get('parentLVName') and prior_options.get('parent_lv_name') is not None:
                        effective_options['parentLVName'] = prior_options.get('parent_lv_name')
                    if not effective_options.get('offset'):
                        effective_options['offset'] = deepcopy(prior_options.get('offset', {'x': '0', 'y': '0', 'z': '0'}))
                    if 'smartImport' not in effective_options and 'smart_import' not in effective_options:
                        effective_options['smartImport'] = bool(prior_options.get('smart_import_enabled', False))

            # The STEP parser now takes the options dictionary
            imported_state = parse_step_file(temp_path, effective_options)
            reimport_diff_summary = None
            if target_import_record is not None:
                reimport_diff_summary = _build_step_import_reimport_diff_summary(
                    self.current_geometry_state,
                    target_import_record,
                    imported_state,
                )

            cad_import_record = _build_step_import_provenance_record(
                temp_path,
                step_file_stream,
                effective_options,
                imported_state,
                import_id=target_import_id,
            )
            smart_import_summary = _build_step_import_smart_import_summary(getattr(imported_state, 'smart_import_report', None))
            if smart_import_summary is not None:
                cad_import_record['smart_import_summary'] = smart_import_summary
            if reimport_diff_summary is not None:
                reimport_diff_summary['cleanup_policy'] = _build_step_import_reimport_cleanup_policy(reimport_diff_summary)
                cad_import_record['reimport_diff_summary'] = reimport_diff_summary
            imported_state.cad_imports = list(getattr(imported_state, 'cad_imports', []) or [])
            imported_state.cad_imports.append(cad_import_record)

            import_report = getattr(imported_state, 'smart_import_report', None)
            annotation_snapshot = None

            if target_import_record is not None:
                annotation_snapshot = self._snapshot_step_import_annotations(target_import_record)
                self.begin_transaction()
                delete_success, delete_error = self._delete_step_import_subsystem(target_import_record)
                if not delete_success:
                    self.abort_transaction()
                    return False, f"Failed to reimport STEP geometry: {delete_error}", None

                if isinstance(getattr(self.current_geometry_state, 'cad_imports', None), list) and target_import_index is not None:
                    del self.current_geometry_state.cad_imports[target_import_index]
            else:
                target_import_index = None

            # The merge_from_state function already handles placements and grouping
            success, error_msg = self.merge_from_state(imported_state)
            
            if not success:
                if target_import_record is not None:
                    self.abort_transaction()
                return False, f"Failed to merge STEP geometry: {error_msg}", None

            if annotation_snapshot is not None:
                self._restore_step_import_annotations(annotation_snapshot)

            # Set the new solids as "changed" so they will be sent to the front end.
            newly_created_solid_names = {solid.name for solid in imported_state.solids.values()}
            self.changed_object_ids['solids'].update(newly_created_solid_names)
            print(f"Changed solids {self.changed_object_ids['solids']}")
            
            # Recalculate is handled inside merge_from_state, but an extra one ensures consistency.
            self.recalculate_geometry_state()
            
            # Capture this entire import as a single history event.
            if target_import_record is not None:
                self.end_transaction(f"Reimported STEP file '{effective_options.get('groupingName')}'")
            else:
                self._capture_history_state(f"Imported STEP file '{effective_options.get('groupingName')}'")

            return True, None, import_report
            
        except Exception as e:
            if target_import_record is not None:
                self.abort_transaction()
            # Ensure we raise the error to be caught by the app route
            raise e
        finally:
            # Clean up the temporary file
            os.unlink(temp_path)

    def create_group(self, group_type, group_name):
        """Creates a new, empty group for a specific object type."""
        if not self.current_geometry_state:
            return False, "No project loaded."
        if group_type not in self.current_geometry_state.ui_groups:
            return False, f"Invalid group type: {group_type}"
        
        # Check for name collision
        if any(g['name'] == group_name for g in self.current_geometry_state.ui_groups[group_type]):
            return False, f"A group named '{group_name}' already exists for {group_type}."
            
        self.current_geometry_state.ui_groups[group_type].append({
            "name": group_name,
            "members": []
        })
        
        # Capture the new state
        self._capture_history_state(f"Created {group_type} group {group_name}")

        return True, None

    def rename_group(self, group_type, old_name, new_name):
        """Renames an existing group."""
        if not self.current_geometry_state:
            return False, "No project loaded."
        if group_type not in self.current_geometry_state.ui_groups:
            return False, f"Invalid group type: {group_type}"
        
        groups = self.current_geometry_state.ui_groups[group_type]
        
        # Check if the new name is already taken (by a different group)
        if any(g['name'] == new_name for g in groups if g['name'] != old_name):
            return False, f"A group named '{new_name}' already exists."

        target_group = next((g for g in groups if g['name'] == old_name), None)
        if not target_group:
            return False, f"Group '{old_name}' not found."
            
        target_group['name'] = new_name

        # Capture the new state
        self._capture_history_state(f"Renamed {group_type} group {old_name} to {new_name}")

        return True, None

    def delete_group(self, group_type, group_name):
        """Deletes a group. Its members become ungrouped."""
        if not self.current_geometry_state:
            return False, "No project loaded."
        if group_type not in self.current_geometry_state.ui_groups:
            return False, f"Invalid group type: {group_type}"

        groups = self.current_geometry_state.ui_groups[group_type]
        
        group_to_delete = next((g for g in groups if g['name'] == group_name), None)
        if not group_to_delete:
            return False, f"Group '{group_name}' not found."
            
        self.current_geometry_state.ui_groups[group_type] = [g for g in groups if g['name'] != group_name]

        # Capture the new state
        self._capture_history_state(f"Deleted {group_type} group {group_name}")

        return True, None

    def move_items_to_group(self, group_type, item_ids, target_group_name):
        """Moves a list of items to a target group, removing them from any previous group."""
        if not self.current_geometry_state:
            return False, "No project loaded."
        if group_type not in self.current_geometry_state.ui_groups:
            return False, f"Invalid group type: {group_type}"

        groups = self.current_geometry_state.ui_groups[group_type]
        item_ids_set = set(item_ids)

        # 1. Remove items from their old groups
        for group in groups:
            group['members'] = [member_id for member_id in group['members'] if member_id not in item_ids_set]

        # 2. Add items to the new group (if a target group is specified)
        if target_group_name:
            target_group = next((g for g in groups if g['name'] == target_group_name), None)
            if not target_group:
                return False, f"Target group '{target_group_name}' not found."
            
            # Add only items that aren't already there to prevent duplicates
            for item_id in item_ids:
                if item_id not in target_group['members']:
                    target_group['members'].append(item_id)
        
        # Capture the new state
        self._capture_history_state(f"Moved items to {group_type} group {target_group_name}")

        # If target_group_name is None, the items are effectively moved to "ungrouped".
        return True, None

    def add_optical_surface(self, name_suggestion, params):
        """Adds a new optical surface to the project."""
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.optical_surfaces)
        
        new_surface = OpticalSurface(
            name=name,
            model=params.get('model'),
            finish=params.get('finish'),
            surf_type=params.get('surf_type'),
            value=params.get('value'),
        )
        new_surface.properties = params.get('properties', {})
        
        self.current_geometry_state.add_optical_surface(new_surface)
        self.recalculate_geometry_state() # Recalculate if any values are expressions

        # Capture the new state
        self._capture_history_state(f"Added optical surface {name}")
        
        return new_surface.to_dict(), None

    def update_optical_surface(self, surface_name, new_params):
        """Updates an existing optical surface."""
        if not self.current_geometry_state:
            return False, "No project loaded"
        
        target_surface = self.current_geometry_state.optical_surfaces.get(surface_name)
        if not target_surface:
            return False, f"Optical Surface '{surface_name}' not found."

        # Update attributes from the params dictionary
        target_surface.model = new_params.get('model', target_surface.model)
        target_surface.finish = new_params.get('finish', target_surface.finish)
        target_surface.type = new_params.get('surf_type', target_surface.type)
        target_surface.value = new_params.get('value', target_surface.value)
        target_surface.properties = new_params.get('properties', target_surface.properties)

        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated optical surface {surface_name}")

        return True, None

    def add_skin_surface(self, name_suggestion, volume_ref, surface_ref):
        """Adds a new skin surface link to the project."""
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        state = self.current_geometry_state
        
        # Validate references
        if volume_ref not in state.logical_volumes:
            return None, f"Logical Volume '{volume_ref}' not found."
        if surface_ref not in state.optical_surfaces:
            return None, f"Optical Surface '{surface_ref}' not found."

        name = self._generate_unique_name(name_suggestion, state.skin_surfaces)
        
        new_skin_surface = SkinSurface(
            name=name,
            volume_ref=volume_ref,
            surfaceproperty_ref=surface_ref
        )
        
        state.add_skin_surface(new_skin_surface)
        # No recalculation is needed as this is just a link, but we'll do it for consistency.
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added skin surface {name}")
        
        return new_skin_surface.to_dict(), None

    def update_skin_surface(self, surface_name, new_volume_ref, new_surface_ref):
        """Updates an existing skin surface link."""
        if not self.current_geometry_state:
            return False, "No project loaded"
        
        state = self.current_geometry_state
        target_surface = state.skin_surfaces.get(surface_name)
        if not target_surface:
            return False, f"Skin Surface '{surface_name}' not found."

        # Validate new references before applying them
        if new_volume_ref not in state.logical_volumes:
            return False, f"New Logical Volume '{new_volume_ref}' not found."
        if new_surface_ref not in state.optical_surfaces:
            return False, f"New Optical Surface '{new_surface_ref}' not found."

        # Update attributes
        target_surface.volume_ref = new_volume_ref
        target_surface.surfaceproperty_ref = new_surface_ref

        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated skin surface {surface_name}")

        return True, None

    def _find_pv_by_id(self, pv_id):
        """Helper to find a PV object by its UUID across the entire geometry."""
        state = self.current_geometry_state
        # Search in Logical Volumes
        for lv in state.logical_volumes.values():
            if lv.content_type == 'physvol':
                for pv in lv.content:
                    if pv.id == pv_id:
                        return pv
        # Search in Assemblies
        for asm in state.assemblies.values():
            for pv in asm.placements:
                if pv.id == pv_id:
                    return pv
        return None

    def add_border_surface(self, name_suggestion, pv1_ref_id, pv2_ref_id, surface_ref):
        """Adds a new border surface link to the project."""
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        state = self.current_geometry_state
        
        # Validate references
        if not self._find_pv_by_id(pv1_ref_id):
            return None, f"Physical Volume 1 (ID: {pv1_ref_id}) not found."
        if not self._find_pv_by_id(pv2_ref_id):
            return None, f"Physical Volume 2 (ID: {pv2_ref_id}) not found."
        if surface_ref not in state.optical_surfaces:
            return None, f"Optical Surface '{surface_ref}' not found."

        name = self._generate_unique_name(name_suggestion, state.border_surfaces)
        
        new_border_surface = BorderSurface(
            name=name,
            physvol1_ref=pv1_ref_id,
            physvol2_ref=pv2_ref_id,
            surfaceproperty_ref=surface_ref
        )
        
        state.add_border_surface(new_border_surface)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added border surface {name}")
        
        return new_border_surface.to_dict(), None

    def update_border_surface(self, surface_name, new_pv1_ref_id, new_pv2_ref_id, new_surface_ref):
        """Updates an existing border surface link."""
        if not self.current_geometry_state:
            return False, "No project loaded"
        
        state = self.current_geometry_state
        target_surface = state.border_surfaces.get(surface_name)
        if not target_surface:
            return False, f"Border Surface '{surface_name}' not found."

        # Validate new references
        if not self._find_pv_by_id(new_pv1_ref_id):
            return False, f"New Physical Volume 1 (ID: {new_pv1_ref_id}) not found."
        if not self._find_pv_by_id(new_pv2_ref_id):
            return False, f"New Physical Volume 2 (ID: {new_pv2_ref_id}) not found."
        if new_surface_ref not in state.optical_surfaces:
            return False, f"New Optical Surface '{new_surface_ref}' not found."

        # Update attributes
        target_surface.physvol1_ref = new_pv1_ref_id
        target_surface.physvol2_ref = new_pv2_ref_id
        target_surface.surfaceproperty_ref = new_surface_ref

        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated border surface {surface_name}")

        return True, None

    def _normalize_gps_commands(self, gps_commands):
        """Normalize gps_commands values to strings to prevent [object Object] display issues."""
        normalized = {}
        key_aliases = {
            '/gps/particle': 'particle',
            'particle_type': 'particle',
            'particle_name': 'particle',
            'distribution': 'ang/type',
            'angular_distribution': 'ang/type',
            'ang/distribution': 'ang/type',
            'direction': 'ang/dir1',
            'beam_direction': 'ang/dir1',
            'ang/direction': 'ang/dir1',
            'ang/dir': 'ang/dir1',
            '/gps/ang/type': 'ang/type',
            '/gps/ang/dir1': 'ang/dir1',
            '/gps/energy': 'energy',
        }
        
        if gps_commands:
            for key, value in gps_commands.items():
                raw_key = str(key).strip()
                key_lookup = raw_key.lower()
                if key_lookup.startswith('/gps/'):
                    key_lookup = key_lookup[5:]
                norm_key = key_aliases.get(key_lookup, key_aliases.get(raw_key.lower(), raw_key))

                if isinstance(value, dict):
                    # Convert {"value": 100, "unit": "keV"} to "100 keV"
                    if 'value' in value and 'unit' in value:
                        normalized[norm_key] = f"{value['value']} {value['unit']}"
                    else:
                        normalized[norm_key] = str(value)
                elif value is None:
                    normalized[norm_key] = ""
                else:
                    normalized[norm_key] = str(value)

        particle_aliases = {
            'electron': 'e-',
            'electron-': 'e-',
            'e_minus': 'e-',
            'e minus': 'e-',
            'positron': 'e+',
            'positron+': 'e+',
            'e_plus': 'e+',
            'e plus': 'e+',
            'photon': 'gamma',
        }
        particle = normalized.get('particle')
        if particle:
            normalized['particle'] = particle_aliases.get(str(particle).strip().lower(), str(particle).strip())
        
        # Set sensible defaults for missing GPS commands
        # Particle type - default to gamma if not specified
        if 'particle' not in normalized or not normalized.get('particle'):
            normalized['particle'] = 'gamma'
        
        # Direction mode - default to Direction (not Isotropic) if not specified.
        ang_type = str(normalized.get('ang/type', '')).strip().lower()
        if ang_type in {'isotropic', 'iso'}:
            normalized['ang/type'] = 'iso'
        elif ang_type in {'direction', 'directed', 'beam', 'beam1d', 'mono', 'monodirectional', 'pencil', 'pencilbeam', 'pencil_beam'}:
            normalized['ang/type'] = 'beam1d'
        elif 'ang/type' not in normalized or not normalized.get('ang/type'):
            normalized['ang/type'] = 'beam1d'
        
        # Energy format - ensure proper Geant4 format with * operator
        if 'energy' in normalized and normalized['energy']:
            energy_str = normalized['energy']
            # Convert "1 GeV" to "1*GeV" format for Geant4
            if ' ' in energy_str and '*' not in energy_str:
                parts = energy_str.strip().split()
                if len(parts) == 2:
                    normalized['energy'] = f"{parts[0]}*{parts[1]}"
        
        return normalized

    def add_source(self, name_suggestion, gps_commands, position, rotation, activity=1.0, confine_to_pv=None, volume_link_id=None):
        """Adds a new particle source to the project, optionally linked to a volume."""
        if not self.current_geometry_state:
            return None, "No project loaded"

        # Normalize gps_commands to ensure all values are strings
        gps_commands = self._normalize_gps_commands(gps_commands)
        
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.sources)
        
        linked_pv = self._find_pv_by_id(volume_link_id) if volume_link_id else None

        new_source = ParticleSource(
            name=name,
            gps_commands=gps_commands,
            position=position,
            rotation=rotation,
            activity=activity,
            confine_to_pv=confine_to_pv,
            volume_link_id=volume_link_id
        )

        if linked_pv:
            self._sync_linked_source_to_pv(new_source, linked_pv, force_confine_name=False)

        self.current_geometry_state.add_source(new_source)
        
        # Auto-activate new manually created sources
        if new_source.id not in self.current_geometry_state.active_source_ids:
            self.current_geometry_state.active_source_ids.append(new_source.id)
            
        self.recalculate_geometry_state()
        self._capture_history_state(f"Added particle source {name}")
        
        return new_source.to_dict(), None

    def update_particle_source(self, source_id, new_name, new_gps_commands, new_position, new_rotation, new_activity=None, new_confine_to_pv=None, new_volume_link_id=None):
        """Updates the properties of an existing particle source."""
        if not self.current_geometry_state:
            return False, "No project loaded"

        source_to_update = None
        for source in self.current_geometry_state.sources.values():
            if source.id == source_id:
                source_to_update = source
                break

        if not source_to_update:
            return False, f"Source with ID '{source_id}' not found."

        # Check for name change and ensure uniqueness if it changed
        if new_name and new_name != source_to_update.name:
            if new_name in self.current_geometry_state.sources:
                return False, f"A source named '{new_name}' already exists."
            # To rename, we remove the old entry and add a new one
            del self.current_geometry_state.sources[source_to_update.name]
            source_to_update.name = new_name
            self.current_geometry_state.sources[new_name] = source_to_update

        if new_gps_commands is not None:
            # Normalize gps_commands to ensure all values are strings
            source_to_update.gps_commands = self._normalize_gps_commands(new_gps_commands)

        if new_position is not None:
            source_to_update.position = new_position

        if new_rotation is not None:
            source_to_update.rotation = new_rotation
        
        if new_activity is not None:
            # simple validation
            try:
                source_to_update.activity = float(new_activity)
            except ValueError:
                return False, f"Invalid activity value: {new_activity}"
        
        if new_confine_to_pv is not None:
            # We treat an empty string as "no confinement" (None)
            if new_confine_to_pv == "":
                source_to_update.confine_to_pv = None
            else:
                source_to_update.confine_to_pv = new_confine_to_pv
        
        # Handle Linked Volume Updates
        source_to_update.volume_link_id = new_volume_link_id
        if source_to_update.volume_link_id:
            pv = self._find_pv_by_id(source_to_update.volume_link_id)
            if pv:
                self._sync_linked_source_to_pv(source_to_update, pv)
            else:
                # Linked ID not found? Maybe deleted. Clear link.
                source_to_update.volume_link_id = None

        self._capture_history_state(f"Updated particle source {source_to_update.name}")
        # Recalculation is not strictly necessary unless commands affect evaluation,
        # but it's good practice to keep it consistent.
        success, error_msg = self.recalculate_geometry_state()
        return success, error_msg
    
    def set_active_source(self, source_id):
        """Sets or toggles the active source for the simulation."""
        if not self.current_geometry_state:
            return False, "No project loaded"

        # If source_id is None, clear all active sources
        if source_id is None:
            self.current_geometry_state.active_source_ids = []
            self.is_changed = True
            return True, "All sources deactivated."

        # Verify the source ID exists
        found = any(s.id == source_id for s in self.current_geometry_state.sources.values())
        if not found:
            return False, f"Source with ID {source_id} not found."

        # Toggle logic: if present, remove it; if absent, add it.
        if source_id in self.current_geometry_state.active_source_ids:
            self.current_geometry_state.active_source_ids.remove(source_id)
            msg = "Source deactivated."
        else:
            self.current_geometry_state.active_source_ids.append(source_id)
            msg = "Source activated."

        self.is_changed = True
        return True, msg

    def _find_pv_by_name(self, pv_name):
        """Helper to find a PV object by its Name across the entire geometry."""
        state = self.current_geometry_state
        # Search in Logical Volumes
        for lv in state.logical_volumes.values():
            if lv.content_type == 'physvol':
                for pv in lv.content:
                    if pv.name == pv_name:
                        return pv
        # Search in Assemblies
        for asm in state.assemblies.values():
            for pv in asm.placements:
                    if pv.name == pv_name:
                        return pv
        return None

    def _find_pvs_by_lv_name(self, lv_name):
        """Returns all placements that instantiate the given logical volume."""
        placements = []
        state = self.current_geometry_state

        for lv in state.logical_volumes.values():
            if lv.content_type == 'physvol':
                for pv in lv.content:
                    if pv.volume_ref == lv_name:
                        placements.append(pv)

        for asm in state.assemblies.values():
            for pv in asm.placements:
                if pv.volume_ref == lv_name:
                    placements.append(pv)

        return placements

    def _logical_volume_is_instantiated_in_scene(self, lv_name):
        """Returns True when the logical volume currently has at least one live scene instance."""
        state = self.current_geometry_state
        if not state or not lv_name:
            return False
        if lv_name == state.world_volume_ref:
            return True

        for scene_item in state.get_threejs_scene_description():
            if scene_item.get('is_source'):
                continue
            if str(scene_item.get('volume_ref') or '').strip() == lv_name:
                return True

        return False

    def _calculate_global_transform_matrix(self, start_pv):
        """Returns the 4x4 global transform matrix for a placed physical volume."""
        state = self.current_geometry_state
        if not state:
            return np.eye(4)

        current_transform = start_pv.get_transform_matrix()
        current_parent_lv_name = start_pv.parent_lv_name

        depth = 0
        max_depth = 20

        while current_parent_lv_name and current_parent_lv_name != state.world_volume_ref and depth < max_depth:
            depth += 1
            parent_placement = None

            found = False
            for lv in state.logical_volumes.values():
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.volume_ref == current_parent_lv_name:
                            parent_placement = pv
                            found = True
                            break
                if found:
                    break

            if not found:
                for asm in state.assemblies.values():
                    for pv in asm.placements:
                        if pv.volume_ref == current_parent_lv_name:
                            parent_placement = pv
                            found = True
                            break
                    if found:
                        break

            if not parent_placement:
                break

            current_transform = parent_placement.get_transform_matrix() @ current_transform
            current_parent_lv_name = parent_placement.parent_lv_name

        return current_transform

    def _calculate_global_transform(self, start_pv):
        """
        Calculates the global position and rotation of a PhysicalVolumePlacement
        by traversing up the hierarchy (finding parents recursively).
        
        Returns:
            global_pos (dict): {'x': float, 'y': float, 'z': float}
            global_rot (dict): {'x': float, 'y': float, 'z': float} (Euler angles in radians)
        """
        state = self.current_geometry_state
        if not state:
            return {'x':0,'y':0,'z':0}, {'x':0,'y':0,'z':0}

        current_transform = self._calculate_global_transform_matrix(start_pv)
        pos_dict, rot_dict, scale_dict = PhysicalVolumePlacement.decompose_matrix(current_transform)
        
        return pos_dict, rot_dict

    def _resolve_incident_beam_target(self, target):
        state = self.current_geometry_state
        target_str = str(target or '').strip()
        if not target_str:
            return None, "A target volume is required."

        pv = self._find_pv_by_id(target_str)
        if pv:
            return pv, None

        pv = self._find_pv_by_name(target_str)
        if pv:
            return pv, None

        if target_str in state.logical_volumes:
            placements = self._find_pvs_by_lv_name(target_str)
            if len(placements) == 1:
                return placements[0], None
            if not placements:
                return None, (
                    f"Logical volume '{target_str}' is not placed anywhere. "
                    "Place it first or target a placed physical volume."
                )
            placement_names = ", ".join(pv.name for pv in placements[:5])
            if len(placements) > 5:
                placement_names += ", ..."
            return None, (
                f"Logical volume '{target_str}' has {len(placements)} placements "
                f"({placement_names}). Target a specific physical volume instead."
            )

        return None, (
            f"Could not resolve target '{target_str}' as a physical volume id/name "
            "or a uniquely placed logical volume."
        )

    def configure_incident_beam(
        self,
        *,
        target,
        particle,
        energy,
        incident_axis='+z',
        offset='1*mm',
        source_name='incident_beam',
        activity=1.0,
        mark_target_sensitive=True,
        activate=True,
        exclusive_activation=True,
    ):
        """Create or update a directed beam source aimed through a target center."""
        if not self.current_geometry_state:
            return None, "No project loaded."

        particle_name = str(particle or '').strip()
        if not particle_name:
            return None, "particle is required."

        energy_expr = str(energy or '').strip()
        if not energy_expr:
            return None, "energy is required."

        pv, error = self._resolve_incident_beam_target(target)
        if not pv:
            return None, error

        state = self.current_geometry_state
        lv = state.logical_volumes.get(pv.volume_ref)
        if not lv:
            return None, f"Logical volume '{pv.volume_ref}' for target '{pv.name}' was not found."

        solid = state.solids.get(lv.solid_ref)
        if not solid:
            return None, f"Solid '{lv.solid_ref}' for target '{pv.name}' was not found."

        old_target_sensitive = bool(lv.is_sensitive)
        target_sensitive_updated = False
        if mark_target_sensitive and not old_target_sensitive:
            lv.is_sensitive = True
            target_sensitive_updated = True

        half_extents = self._get_solid_local_half_extents(solid)
        if not half_extents:
            if target_sensitive_updated:
                lv.is_sensitive = old_target_sensitive
            return None, (
                f"Target '{pv.name}' uses unsupported solid type '{solid.type}' for beam setup. "
                "Supported targets currently include box, tube/tubs, sphere, and orb."
            )

        axis_map = {
            '+x': (np.array([1.0, 0.0, 0.0]), 0),
            '-x': (np.array([-1.0, 0.0, 0.0]), 0),
            '+y': (np.array([0.0, 1.0, 0.0]), 1),
            '-y': (np.array([0.0, -1.0, 0.0]), 1),
            '+z': (np.array([0.0, 0.0, 1.0]), 2),
            '-z': (np.array([0.0, 0.0, -1.0]), 2),
        }
        axis_key = str(incident_axis or '+z').strip().lower()
        if axis_key not in axis_map:
            return None, "incident_axis must be one of +x, -x, +y, -y, +z, -z."

        offset_success, offset_value = self.expression_evaluator.evaluate(str(offset), verbose=False)
        if not offset_success:
            return None, f"Invalid offset expression: {offset_value}"

        try:
            offset_mm = float(offset_value)
        except Exception:
            return None, f"Offset '{offset}' did not evaluate to a numeric length."
        if offset_mm < 0:
            return None, "offset must be >= 0."

        try:
            activity_value = float(activity)
        except (TypeError, ValueError):
            return None, f"activity '{activity}' is not numeric."

        local_dir, axis_index = axis_map[axis_key]
        half_extent = float(half_extents[axis_index])

        global_matrix = self._calculate_global_transform_matrix(pv)
        center = np.asarray(global_matrix[:3, 3], dtype=float)

        rotation_scale = np.asarray(global_matrix[:3, :3], dtype=float).copy()
        for idx in range(3):
            norm = np.linalg.norm(rotation_scale[:, idx])
            if norm > 1e-12:
                rotation_scale[:, idx] /= norm

        global_dir = rotation_scale @ local_dir
        dir_norm = np.linalg.norm(global_dir)
        if dir_norm <= 1e-12:
            if target_sensitive_updated:
                lv.is_sensitive = old_target_sensitive
            return None, f"Could not determine a valid beam direction for target '{pv.name}'."
        global_dir = global_dir / dir_norm

        source_pos = center - global_dir * (half_extent + offset_mm)

        def _fmt(value):
            return f"{float(value):.8g}"

        gps_commands = self._normalize_gps_commands({
            'particle': particle_name,
            'energy': energy_expr,
            'pos/type': 'Point',
            'ang/type': 'beam1d',
            'ang/dir1': f"{_fmt(global_dir[0])} {_fmt(global_dir[1])} {_fmt(global_dir[2])}",
        })

        position = {
            'x': _fmt(source_pos[0]),
            'y': _fmt(source_pos[1]),
            'z': _fmt(source_pos[2]),
        }
        rotation = {'x': '0', 'y': '0', 'z': '0'}

        old_active_source_ids = list(self.current_geometry_state.active_source_ids)
        old_source_snapshot = None

        existing_source = self.current_geometry_state.sources.get(source_name)
        if existing_source:
            old_source_snapshot = deepcopy(existing_source.to_dict())
            existing_source.gps_commands = gps_commands
            existing_source.position = position
            existing_source.rotation = rotation
            existing_source.activity = activity_value
            existing_source.confine_to_pv = None
            existing_source.volume_link_id = None
            source_obj = existing_source
            action = 'updated'
        else:
            final_name = self._generate_unique_name(source_name, self.current_geometry_state.sources)
            source_obj = ParticleSource(
                final_name,
                gps_commands,
                position,
                rotation,
                activity=activity_value,
                confine_to_pv=None,
                volume_link_id=None,
            )
            self.current_geometry_state.add_source(source_obj)
            action = 'created'

        if activate:
            if exclusive_activation:
                self.current_geometry_state.active_source_ids = [source_obj.id]
            elif source_obj.id not in self.current_geometry_state.active_source_ids:
                self.current_geometry_state.active_source_ids.append(source_obj.id)

        success, error_msg = self.recalculate_geometry_state()
        if not success:
            lv.is_sensitive = old_target_sensitive
            if old_source_snapshot is not None:
                restored = ParticleSource.from_dict(old_source_snapshot)
                self.current_geometry_state.sources[restored.name] = restored
            else:
                self.current_geometry_state.sources.pop(source_obj.name, None)
            self.current_geometry_state.active_source_ids = old_active_source_ids
            self.recalculate_geometry_state()
            return None, error_msg

        self._capture_history_state(
            f"Configured incident beam {source_obj.name} for target {pv.name}"
        )

        return {
            'id': source_obj.id,
            'name': source_obj.name,
            'action': action,
            'gps_commands': source_obj.gps_commands,
            'position': source_obj.position,
            'rotation': source_obj.rotation,
            'activity': source_obj.activity,
            'target_pv_id': pv.id,
            'target_pv_name': pv.name,
            'target_lv_name': lv.name,
            'target_is_sensitive': bool(lv.is_sensitive),
            'target_sensitive_updated': bool(target_sensitive_updated),
            'incident_axis': axis_key,
            'direction_vector': {
                'x': float(global_dir[0]),
                'y': float(global_dir[1]),
                'z': float(global_dir[2]),
            },
            'offset_mm': offset_mm,
            'activated': bool(activate),
            'exclusive_activation': bool(exclusive_activation),
        }, None

    
    def get_source_params_from_volume(self, volume_id):
        """
        Calculates the appropriate GPS source parameters to emulate a source bound to the specified PhysicalVolume.
        Returns a dictionary with position, rotation, shape type, and shape dimensions.
        """
        pv = self._find_pv_by_id(volume_id)
        if not pv:
            return {'success': False, 'error': f"Physical Volume with ID {volume_id} not found."}

        # 1. Calculate Global Transform (Position & Rotation)
        global_pos, global_rot_rad = self._calculate_global_transform(pv)

        # 2. Determine Shape Parameters from the linked Solid
        state = self.current_geometry_state
        lv = state.logical_volumes.get(pv.volume_ref)
        if not lv:
            return {'success': False, 'error': f"Logical Volume {pv.volume_ref} not found."}
        
        solid = state.solids.get(lv.solid_ref)
        if not solid:
            return {'success': False, 'error': f"Solid {lv.solid_ref} not found."}
        
        # Helper to format float to string
        fstr = lambda x: str(x)
        
        # Default shape commands
        shape_type = 'Volume'
        gps_shape_type = 'Sphere' # Default sub-shape
        shape_params = {}

        p = solid._evaluated_parameters
        
        if solid.type in ['box']:
            gps_shape_type = 'Box'
            # GPS Box uses half-lengths
            shape_params['gps_halfx'] = fstr(p.get('x', 0)/2)
            shape_params['gps_halfy'] = fstr(p.get('y', 0)/2)
            shape_params['gps_halfz'] = fstr(p.get('z', 0)/2)

        elif solid.type in ['tube', 'cylinder', 'tubs']:
            gps_shape_type = 'Cylinder'
            shape_params['gps_radius'] = fstr(p.get('rmax', 0))
            shape_params['gps_halfz'] = fstr(p.get('z', 0)/2)
            
        elif solid.type in ['sphere', 'orb']:
            gps_shape_type = 'Sphere'
            shape_params['gps_radius'] = fstr(p.get('rmax', 0))
        
        else:
            # Fallback for complex shapes: use bounding box approximation?
            # For now, default to a generic Sphere with radius 10
            gps_shape_type = 'Sphere'
            shape_params['gps_radius'] = '10'

        return {
            'success': True,
            'position': {
                'x': fstr(global_pos['x']),
                'y': fstr(global_pos['y']),
                'z': fstr(global_pos['z'])
            },
            'rotation': {
                'x': fstr(global_rot_rad['x']),
                'y': fstr(global_rot_rad['y']),
                'z': fstr(global_rot_rad['z'])
            },
            'shape_type': shape_type,
            'gps_shape_type': gps_shape_type,
            'shape_params': shape_params,
            'confine_pv_name': pv.name
        }

    def _calculate_bounding_params(self, pv_name):
        """
        Finds the PV, looks up its Logical Volume and Solid, 
        and returns appropriate GPS shape params and the PV's evaluated transform.
        """
        pv = self._find_pv_by_name(pv_name)
        if not pv: return None, None, None
        
        # Look up LV
        lv = self.current_geometry_state.logical_volumes.get(pv.volume_ref)
        if not lv: return None, None, None
        
        solid = self.current_geometry_state.solids.get(lv.solid_ref)
        if not solid: return None, None, None

        # Determine tight bounding box based on Solid Type
        p = solid._evaluated_parameters # These are already in mm/rad
        
        shape_cmds = {'pos/shape': 'Para'} 
        
        if solid.type == 'box':
            shape_cmds['pos/halfx'] = f"{p['x']/2} mm"
            shape_cmds['pos/halfy'] = f"{p['y']/2} mm"
            shape_cmds['pos/halfz'] = f"{p['z']/2} mm"
        
        elif solid.type in ['tube', 'cylinder']:
            # For a cylinder, a bounding box is 2*R by 2*R by Z
            shape_cmds['pos/halfx'] = f"{p['rmax']} mm"
            shape_cmds['pos/halfy'] = f"{p['rmax']} mm"
            shape_cmds['pos/halfz'] = f"{p['z']/2} mm"

        elif solid.type == 'sphere':
            shape_cmds['pos/halfx'] = f"{p['rmax']} mm"
            shape_cmds['pos/halfy'] = f"{p['rmax']} mm"
            shape_cmds['pos/halfz'] = f"{p['rmax']} mm"

        else:
            # Fallback for complex shapes
            shape_cmds['pos/halfx'] = "200 mm" 
            shape_cmds['pos/halfy'] = "200 mm" 
            shape_cmds['pos/halfz'] = "200 mm"
        
        return shape_cmds, pv._evaluated_position, pv._evaluated_rotation

    def _preflight_add_issue(self, report, severity, code, message, object_refs=None, hint=None, metadata=None):
        issue = {
            'severity': severity,
            'code': code,
            'message': message,
            'object_refs': object_refs or [],
        }
        if hint:
            issue['hint'] = hint
        if metadata is not None:
            issue['metadata'] = metadata
        report['issues'].append(issue)

    def _preflight_issue_signature(self, issue):
        refs = issue.get('object_refs', [])
        if not isinstance(refs, list):
            refs = [refs]

        return {
            'severity': str(issue.get('severity', 'info')),
            'code': str(issue.get('code', 'unknown')),
            'message': str(issue.get('message', '')),
            'object_refs': [str(ref) for ref in refs],
            'hint': str(issue['hint']) if issue.get('hint') is not None else None,
            'metadata': issue.get('metadata'),
        }

    def _preflight_finalize(self, report):
        severity_counts = {'error': 0, 'warning': 0, 'info': 0}
        code_counts = {}
        signatures = []

        for issue in report['issues']:
            sev = issue.get('severity', 'info')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

            code = issue.get('code', 'unknown')
            code_counts[code] = code_counts.get(code, 0) + 1
            signatures.append(self._preflight_issue_signature(issue))

        sorted_signatures = sorted(
            signatures,
            key=lambda item: (
                item.get('severity', 'info'),
                item.get('code', 'unknown'),
                item.get('message', ''),
                tuple(item.get('object_refs', [])),
                item.get('hint') or '',
                json.dumps(item.get('metadata'), sort_keys=True, separators=(',', ':'), default=str),
            ),
        )

        fingerprint_payload = json.dumps(
            sorted_signatures,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        issue_fingerprint = hashlib.sha256(fingerprint_payload).hexdigest()

        report['summary'] = {
            'errors': severity_counts.get('error', 0),
            'warnings': severity_counts.get('warning', 0),
            'infos': severity_counts.get('info', 0),
            'can_run': severity_counts.get('error', 0) == 0,
            'counts_by_code': dict(sorted(code_counts.items())),
            'issue_count': len(report['issues']),
            'issue_fingerprint': issue_fingerprint,
        }
        return report

    def _get_solid_local_half_extents(self, solid):
        """Returns (hx, hy, hz) for supported primitive solids, else None."""
        p = solid._evaluated_parameters or {}
        solid_type = solid.type

        try:
            if solid_type == 'box':
                return (float(p.get('x', 0.0)) / 2.0, float(p.get('y', 0.0)) / 2.0, float(p.get('z', 0.0)) / 2.0)
            if solid_type in ['tube', 'cylinder', 'tubs']:
                rmax = float(p.get('rmax', 0.0))
                z = float(p.get('z', 0.0))
                return (rmax, rmax, z / 2.0)
            if solid_type in ['sphere']:
                rmax = float(p.get('rmax', 0.0))
                return (rmax, rmax, rmax)
            if solid_type in ['orb']:
                r = float(p.get('r', 0.0))
                return (r, r, r)
        except Exception:
            return None

        return None

    def _compute_pv_aabb(self, pv):
        state = self.current_geometry_state
        lv = state.logical_volumes.get(pv.volume_ref)
        if not lv:
            return None

        solid = state.solids.get(lv.solid_ref)
        if not solid:
            return None

        half_extents = self._get_solid_local_half_extents(solid)
        if not half_extents:
            return None

        hx, hy, hz = half_extents
        if hx <= 0 or hy <= 0 or hz <= 0:
            return None

        corners = np.array([
            [sx * hx, sy * hy, sz * hz, 1.0]
            for sx in (-1.0, 1.0)
            for sy in (-1.0, 1.0)
            for sz in (-1.0, 1.0)
        ])

        matrix = pv.get_transform_matrix()
        transformed = (matrix @ corners.T).T[:, :3]

        mins = transformed.min(axis=0)
        maxs = transformed.max(axis=0)

        return {
            'pv': pv,
            'pv_name': pv.name,
            'pv_id': pv.id,
            'solid_type': solid.type,
            'min': mins,
            'max': maxs,
        }

    def _aabb_intersection_volume(self, a, b):
        overlap = np.minimum(a['max'], b['max']) - np.maximum(a['min'], b['min'])
        if np.any(overlap <= 0):
            return 0.0
        return float(overlap[0] * overlap[1] * overlap[2])

    def _build_preflight_hierarchy_adjacency(self, state):
        adjacency = {}

        for lv_name in sorted(state.logical_volumes.keys()):
            adjacency[f"LV:{lv_name}"] = []
        for asm_name in sorted(state.assemblies.keys()):
            adjacency[f"ASM:{asm_name}"] = []

        for parent_lv in state.logical_volumes.values():
            parent_node = f"LV:{parent_lv.name}"

            if parent_lv.content_type == 'physvol':
                if not parent_lv.content:
                    continue
                for pv in parent_lv.content:
                    placed_ref = str(getattr(pv, 'volume_ref', '') or '').strip()
                    if placed_ref in state.logical_volumes:
                        adjacency[parent_node].append(f"LV:{placed_ref}")
                    elif placed_ref in state.assemblies:
                        adjacency[parent_node].append(f"ASM:{placed_ref}")
                continue

            if parent_lv.content_type in ['replica', 'division', 'parameterised'] and parent_lv.content:
                placed_ref = str(getattr(parent_lv.content, 'volume_ref', '') or '').strip()
                if placed_ref in state.logical_volumes:
                    adjacency[parent_node].append(f"LV:{placed_ref}")

        for asm in state.assemblies.values():
            parent_node = f"ASM:{asm.name}"
            for pv in asm.placements:
                placed_ref = str(getattr(pv, 'volume_ref', '') or '').strip()
                if placed_ref in state.logical_volumes:
                    adjacency[parent_node].append(f"LV:{placed_ref}")
                elif placed_ref in state.assemblies:
                    adjacency[parent_node].append(f"ASM:{placed_ref}")

        for node_name, child_nodes in adjacency.items():
            adjacency[node_name] = sorted(set(child_nodes))

        return adjacency

    def _normalize_preflight_cycle_signature(self, cycle_nodes):
        if not cycle_nodes:
            return tuple()

        if len(cycle_nodes) > 1 and cycle_nodes[0] == cycle_nodes[-1]:
            core = list(cycle_nodes[:-1])
        else:
            core = list(cycle_nodes)

        if len(core) <= 1:
            return tuple(core)

        rotations = [
            tuple(core[idx:] + core[:idx])
            for idx in range(len(core))
        ]
        return min(rotations)

    def _find_preflight_hierarchy_cycles(self, state, max_cycles=20):
        adjacency = self._build_preflight_hierarchy_adjacency(state)
        visited = set()
        active_index = {}
        active_stack = []

        try:
            max_cycles = int(max_cycles)
        except Exception:
            max_cycles = 20

        if max_cycles < 1:
            max_cycles = 1

        cycles = []
        seen_signatures = set()
        truncated = False

        def _record_cycle(cycle_path):
            nonlocal truncated
            signature = self._normalize_preflight_cycle_signature(cycle_path)
            if signature in seen_signatures:
                return False

            seen_signatures.add(signature)
            cycles.append(cycle_path)
            if len(cycles) >= max_cycles:
                truncated = True
                return True
            return False

        def _dfs(node_name):
            visited.add(node_name)
            active_index[node_name] = len(active_stack)
            active_stack.append(node_name)

            for child_name in adjacency.get(node_name, []):
                if child_name in active_index:
                    cycle_start_idx = active_index[child_name]
                    cycle_path = active_stack[cycle_start_idx:] + [child_name]
                    if _record_cycle(cycle_path):
                        return True
                    continue

                if child_name in visited:
                    continue

                if _dfs(child_name):
                    return True

            active_stack.pop()
            active_index.pop(node_name, None)
            return False

        for node_name in sorted(adjacency.keys()):
            if node_name in visited:
                continue
            if _dfs(node_name):
                break

        metadata = {
            'max_cycles': max_cycles,
            'reported_cycles': len(cycles),
            'truncated': truncated,
        }
        return cycles, metadata

    def run_preflight_checks(self):
        """Runs lightweight geometry preflight checks prior to simulation."""
        report = {
            'version': 1,
            'name': 'geometry_preflight_v1',
            'issues': [],
        }

        if not self.current_geometry_state:
            self._preflight_add_issue(report, 'error', 'missing_project_state', 'No project geometry state is loaded.')
            return self._preflight_finalize(report)

        ok, err = self.recalculate_geometry_state()
        if not ok:
            self._preflight_add_issue(
                report,
                'error',
                'recalculation_failed',
                f'Geometry evaluation failed: {err}',
                hint='Fix invalid expressions/defines before simulation.',
            )
            return self._preflight_finalize(report)

        state = self.current_geometry_state

        # 1) Root/world and placement reference integrity checks.
        world_volume_ref = str(state.world_volume_ref or '').strip()
        if not world_volume_ref:
            self._preflight_add_issue(
                report,
                'error',
                'missing_world_volume_reference',
                'Project is missing world_volume_ref.',
                hint='Set a valid world volume before running simulation.',
            )
        elif world_volume_ref not in state.logical_volumes:
            self._preflight_add_issue(
                report,
                'error',
                'unknown_world_volume_reference',
                f"World volume '{world_volume_ref}' was not found in logical volumes.",
                object_refs=[world_volume_ref],
                hint='Set world_volume_ref to an existing logical volume.',
            )

        for parent_lv in state.logical_volumes.values():
            if parent_lv.content_type != 'physvol' or not parent_lv.content:
                continue

            for pv in parent_lv.content:
                placed_ref = str(getattr(pv, 'volume_ref', '') or '').strip()
                if not placed_ref:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'missing_placement_volume_reference',
                        f"Placement '{pv.name}' in parent LV '{parent_lv.name}' has no volume_ref.",
                        object_refs=[pv.id, parent_lv.name],
                        hint='Set this placement to reference a logical volume or assembly.',
                    )
                    continue

                if placed_ref not in state.logical_volumes and placed_ref not in state.assemblies:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'unknown_placement_volume_reference',
                        (
                            f"Placement '{pv.name}' in parent LV '{parent_lv.name}' references missing volume "
                            f"or assembly '{placed_ref}'."
                        ),
                        object_refs=[pv.id, parent_lv.name, placed_ref],
                        hint='Update or remove the stale placement reference.',
                    )

                if world_volume_ref and placed_ref == world_volume_ref:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'world_volume_referenced_as_child',
                        (
                            f"Placement '{pv.name}' in parent LV '{parent_lv.name}' references the world volume "
                            f"'{world_volume_ref}' as a child."
                        ),
                        object_refs=[pv.id, parent_lv.name, world_volume_ref],
                        hint='World volume must be the root and should not be placed under another volume.',
                    )

        for asm in state.assemblies.values():
            for pv in asm.placements:
                placed_ref = str(getattr(pv, 'volume_ref', '') or '').strip()
                if not placed_ref:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'missing_placement_volume_reference',
                        f"Assembly placement '{pv.name}' in assembly '{asm.name}' has no volume_ref.",
                        object_refs=[pv.id, asm.name],
                        hint='Set this assembly placement to reference a logical volume or assembly.',
                    )
                    continue

                if placed_ref not in state.logical_volumes and placed_ref not in state.assemblies:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'unknown_placement_volume_reference',
                        (
                            f"Assembly placement '{pv.name}' in assembly '{asm.name}' references missing volume "
                            f"or assembly '{placed_ref}'."
                        ),
                        object_refs=[pv.id, asm.name, placed_ref],
                        hint='Update or remove the stale assembly placement reference.',
                    )

                if world_volume_ref and placed_ref == world_volume_ref:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'world_volume_referenced_as_child',
                        (
                            f"Assembly placement '{pv.name}' in assembly '{asm.name}' references the world volume "
                            f"'{world_volume_ref}' as a child."
                        ),
                        object_refs=[pv.id, asm.name, world_volume_ref],
                        hint='World volume must be the root and should not be nested in assemblies.',
                    )

        # 2) Procedural placement reference and bounds checks.
        valid_division_axes = {'kxaxis', 'kyaxis', 'kzaxis', 'x', 'y', 'z', 'krho', 'kphi', 'rho', 'phi'}
        division_axis_to_box_dim = {
            'kxaxis': 'x',
            'kyaxis': 'y',
            'kzaxis': 'z',
            'x': 'x',
            'y': 'y',
            'z': 'z',
        }

        for parent_lv in state.logical_volumes.values():
            if parent_lv.content_type not in ['replica', 'division', 'parameterised']:
                continue

            proc = parent_lv.content
            if not proc:
                self._preflight_add_issue(
                    report,
                    'error',
                    'missing_procedural_placement_definition',
                    (
                        f"LogicalVolume '{parent_lv.name}' is marked as procedural type "
                        f"'{parent_lv.content_type}' but has no content definition."
                    ),
                    object_refs=[parent_lv.name],
                    hint='Recreate this procedural placement definition or switch the LV back to physvol content.',
                )
                continue

            placed_ref = str(getattr(proc, 'volume_ref', '') or '').strip()
            proc_name = str(getattr(proc, 'name', parent_lv.name) or parent_lv.name)

            if not placed_ref:
                self._preflight_add_issue(
                    report,
                    'error',
                    'missing_procedural_volume_reference',
                    (
                        f"Procedural placement '{proc_name}' in LV '{parent_lv.name}' has no volume_ref."
                    ),
                    object_refs=[parent_lv.name],
                    hint='Set this procedural placement to reference an existing logical volume.',
                )
            elif placed_ref not in state.logical_volumes:
                self._preflight_add_issue(
                    report,
                    'error',
                    'unknown_procedural_volume_reference',
                    (
                        f"Procedural placement '{proc_name}' in LV '{parent_lv.name}' references missing "
                        f"logical volume '{placed_ref}'."
                    ),
                    object_refs=[parent_lv.name, placed_ref],
                    hint='Update or remove the stale procedural volume reference.',
                )

            if world_volume_ref and placed_ref == world_volume_ref:
                self._preflight_add_issue(
                    report,
                    'error',
                    'world_volume_referenced_as_child',
                    (
                        f"Procedural placement '{proc_name}' in LV '{parent_lv.name}' references the world volume "
                        f"'{world_volume_ref}' as a child."
                    ),
                    object_refs=[parent_lv.name, world_volume_ref],
                    hint='World volume must be the root and cannot be used as a procedural child target.',
                )

            if parent_lv.content_type == 'replica':
                replica_count = getattr(proc, '_evaluated_number', np.nan)
                replica_width = getattr(proc, '_evaluated_width', np.nan)

                if not np.isfinite(replica_count) or int(replica_count) <= 0:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'invalid_replica_instance_count',
                        (
                            f"Replica placement '{proc_name}' in LV '{parent_lv.name}' has invalid evaluated "
                            f"number={replica_count}."
                        ),
                        object_refs=[parent_lv.name],
                        hint='Replica number must evaluate to an integer > 0.',
                    )

                if not np.isfinite(replica_width) or float(replica_width) <= 0:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'invalid_replica_width',
                        (
                            f"Replica placement '{proc_name}' in LV '{parent_lv.name}' has invalid evaluated "
                            f"width={replica_width}."
                        ),
                        object_refs=[parent_lv.name],
                        hint='Replica width must evaluate to a positive finite value.',
                    )

                direction = getattr(proc, 'direction', {}) or {}
                try:
                    axis_vec = np.array([
                        float(direction.get('x', np.nan)),
                        float(direction.get('y', np.nan)),
                        float(direction.get('z', np.nan)),
                    ])
                except Exception:
                    axis_vec = np.array([np.nan, np.nan, np.nan])

                if not np.all(np.isfinite(axis_vec)) or float(np.linalg.norm(axis_vec)) <= 0.0:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'invalid_replica_direction',
                        (
                            f"Replica placement '{proc_name}' in LV '{parent_lv.name}' has invalid direction "
                            f"vector {direction}."
                        ),
                        object_refs=[parent_lv.name],
                        hint='Replica direction must be a non-zero finite vector.',
                    )

            elif parent_lv.content_type == 'division':
                axis = str(getattr(proc, 'axis', '') or '').strip().lower()
                if axis not in valid_division_axes:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'invalid_division_axis',
                        (
                            f"Division placement '{proc_name}' in LV '{parent_lv.name}' has unsupported axis "
                            f"'{getattr(proc, 'axis', '')}'."
                        ),
                        object_refs=[parent_lv.name],
                        hint='Use one of: kXAxis, kYAxis, kZAxis (or x/y/z aliases).',
                    )

                division_number = getattr(proc, '_evaluated_number', np.nan)
                division_width = getattr(proc, '_evaluated_width', np.nan)

                has_positive_number = np.isfinite(division_number) and float(division_number) > 0
                has_positive_width = np.isfinite(division_width) and float(division_width) > 0

                if not has_positive_number and not has_positive_width:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'invalid_division_partition_bounds',
                        (
                            f"Division placement '{proc_name}' in LV '{parent_lv.name}' has invalid evaluated "
                            f"number={division_number} and width={division_width}."
                        ),
                        object_refs=[parent_lv.name],
                        hint='Division must evaluate to a positive number of slices and/or positive width.',
                    )

                if has_positive_number:
                    axis_key = division_axis_to_box_dim.get(axis)
                    mother_solid = state.solids.get(parent_lv.solid_ref)
                    if axis_key and mother_solid and mother_solid.type == 'box':
                        mother_params = mother_solid._evaluated_parameters or {}
                        mother_extent = float(mother_params.get(axis_key, np.nan))
                        division_offset = getattr(proc, '_evaluated_offset', np.nan)

                        if np.isfinite(mother_extent) and np.isfinite(division_offset):
                            derived_slice_width = (mother_extent - (2.0 * float(division_offset))) / float(division_number)
                            if derived_slice_width <= 0:
                                self._preflight_add_issue(
                                    report,
                                    'error',
                                    'invalid_division_slice_width',
                                    (
                                        f"Division placement '{proc_name}' in LV '{parent_lv.name}' yields non-positive "
                                        f"slice width {derived_slice_width} mm from mother extent {mother_extent} mm "
                                        f"and offset {division_offset} mm."
                                    ),
                                    object_refs=[parent_lv.name],
                                    hint='Reduce division offset or increase mother extent/number settings.',
                                )

            elif parent_lv.content_type == 'parameterised':
                ncopies = getattr(proc, '_evaluated_ncopies', np.nan)
                if not np.isfinite(ncopies) or int(ncopies) <= 0:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'invalid_parameterised_ncopies',
                        (
                            f"Parameterised placement '{proc_name}' in LV '{parent_lv.name}' has invalid evaluated "
                            f"ncopies={ncopies}."
                        ),
                        object_refs=[parent_lv.name],
                        hint='Set ncopies to an integer > 0.',
                    )

                parameter_sets = getattr(proc, 'parameters', None) or []
                if not parameter_sets:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'missing_parameterised_parameters',
                        (
                            f"Parameterised placement '{proc_name}' in LV '{parent_lv.name}' has no parameter sets."
                        ),
                        object_refs=[parent_lv.name],
                        hint='Add at least one parameter block for the parameterised placement.',
                    )
                elif np.isfinite(ncopies) and int(ncopies) > 0 and len(parameter_sets) != int(ncopies):
                    self._preflight_add_issue(
                        report,
                        'warning',
                        'parameterised_parameter_count_mismatch',
                        (
                            f"Parameterised placement '{proc_name}' in LV '{parent_lv.name}' has ncopies={int(ncopies)} "
                            f"but defines {len(parameter_sets)} parameter sets."
                        ),
                        object_refs=[parent_lv.name],
                        hint='Align ncopies with the number of provided parameter sets for deterministic behavior.',
                    )

        # 3) Placement hierarchy cycle checks (LV <-> LV/ASM and ASM <-> LV/ASM).
        hierarchy_cycles, hierarchy_cycle_metadata = self._find_preflight_hierarchy_cycles(state)
        for cycle_path in hierarchy_cycles:
            cycle_str = ' -> '.join(cycle_path)
            self._preflight_add_issue(
                report,
                'error',
                'placement_hierarchy_cycle',
                f'Placement hierarchy contains a recursive cycle: {cycle_str}.',
                object_refs=cycle_path[:-1],
                hint='Break recursive placement loops so the hierarchy becomes acyclic.',
            )

        if hierarchy_cycle_metadata.get('truncated'):
            max_cycles = hierarchy_cycle_metadata.get('max_cycles', len(hierarchy_cycles))
            reported_cycles = hierarchy_cycle_metadata.get('reported_cycles', len(hierarchy_cycles))
            self._preflight_add_issue(
                report,
                'info',
                'placement_hierarchy_cycle_report_truncated',
                (
                    f'Cycle reporting truncated at max_cycles={max_cycles}; '
                    f'reported {reported_cycles} cycle findings.'
                ),
                metadata={
                    'max_cycles': max_cycles,
                    'reported_cycles': reported_cycles,
                    'truncated': True,
                },
            )

        # 4) Missing references and material checks.
        for lv in state.logical_volumes.values():
            if not lv.solid_ref or lv.solid_ref not in state.solids:
                self._preflight_add_issue(
                    report,
                    'error',
                    'missing_solid_reference',
                    f"LogicalVolume '{lv.name}' references missing solid '{lv.solid_ref}'.",
                    object_refs=[lv.name, lv.solid_ref],
                    hint='Assign a valid solid to this logical volume.',
                )

            mat = lv.material_ref
            if not mat:
                self._preflight_add_issue(
                    report,
                    'error',
                    'missing_material_reference',
                    f"LogicalVolume '{lv.name}' has no material assigned.",
                    object_refs=[lv.name],
                    hint='Assign a material before running simulation.',
                )
            elif (mat not in state.materials) and (not str(mat).startswith('G4_')):
                self._preflight_add_issue(
                    report,
                    'error',
                    'unknown_material_reference',
                    f"LogicalVolume '{lv.name}' references unknown material '{mat}'.",
                    object_refs=[lv.name, mat],
                    hint='Create this material or switch to a known/NIST material.',
                )

        if state.sources and not any(bool(lv.is_sensitive) for lv in state.logical_volumes.values()):
            self._preflight_add_issue(
                report,
                'warning',
                'no_sensitive_detectors_defined_for_active_sources',
                (
                    'Particle sources are configured, but no logical volumes are marked sensitive. '
                    'Track visualization may work, but Hits HDF5 outputs will stay empty.'
                ),
                hint='Mark at least one target logical volume as sensitive to record deposited-energy hits.',
            )

        # 5) Solid geometry sanity checks.
        tiny_threshold_mm = 1e-3  # 1 micron in mm units
        for solid in state.solids.values():
            p = solid._evaluated_parameters or {}
            st = solid.type

            def check_positive(name, value):
                if value is None or not np.isfinite(value):
                    self._preflight_add_issue(
                        report,
                        'error',
                        'non_finite_dimension',
                        f"Solid '{solid.name}' has invalid parameter '{name}'={value}.",
                        object_refs=[solid.name],
                        hint='Check expressions/units for this solid parameter.',
                    )
                    return
                if value <= 0:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'non_positive_dimension',
                        f"Solid '{solid.name}' has non-positive '{name}'={value}.",
                        object_refs=[solid.name],
                        hint='Dimensions must be > 0.',
                    )
                elif value < tiny_threshold_mm:
                    self._preflight_add_issue(
                        report,
                        'warning',
                        'tiny_dimension',
                        f"Solid '{solid.name}' has tiny '{name}'={value} mm.",
                        object_refs=[solid.name],
                        hint='Very small features can cause navigation issues.',
                    )

            if st == 'box':
                for key in ['x', 'y', 'z']:
                    check_positive(key, float(p.get(key, np.nan)))
            elif st in ['tube', 'cylinder', 'tubs']:
                check_positive('rmax', float(p.get('rmax', np.nan)))
                check_positive('z', float(p.get('z', np.nan)))
                rmin = float(p.get('rmin', 0.0))
                rmax = float(p.get('rmax', np.nan))
                if np.isfinite(rmin) and np.isfinite(rmax) and rmin >= rmax:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'invalid_radial_bounds',
                        f"Solid '{solid.name}' has rmin >= rmax ({rmin} >= {rmax}).",
                        object_refs=[solid.name],
                        hint='Ensure rmin < rmax for tube-like solids.',
                    )
            elif st in ['sphere']:
                check_positive('rmax', float(p.get('rmax', np.nan)))
                rmin = float(p.get('rmin', 0.0))
                rmax = float(p.get('rmax', np.nan))
                if np.isfinite(rmin) and np.isfinite(rmax) and rmin >= rmax:
                    self._preflight_add_issue(
                        report,
                        'error',
                        'invalid_radial_bounds',
                        f"Solid '{solid.name}' has rmin >= rmax ({rmin} >= {rmax}).",
                        object_refs=[solid.name],
                    )
            elif st == 'tessellated':
                facets = solid.raw_parameters.get('facets', []) if isinstance(solid.raw_parameters, dict) else []
                if len(facets) < 4:
                    self._preflight_add_issue(
                        report,
                        'warning',
                        'low_facet_count',
                        f"Tessellated solid '{solid.name}' has very few facets ({len(facets)}).",
                        object_refs=[solid.name],
                        hint='Check CAD import quality; this may indicate degenerate geometry.',
                    )

        # 6) Approximate sibling overlap checks (AABB heuristic).
        placement_groups = []
        for lv in state.logical_volumes.values():
            if lv.content_type == 'physvol' and lv.content:
                placement_groups.append((f"LV:{lv.name}", lv.content))
        for asm in state.assemblies.values():
            if asm.placements:
                placement_groups.append((f"ASM:{asm.name}", asm.placements))

        max_overlap_reports = 50
        overlap_reports = 0
        for group_name, placements in placement_groups:
            aabbs = []
            for pv in placements:
                box = self._compute_pv_aabb(pv)
                if box is not None:
                    aabbs.append(box)

            for a, b in itertools.combinations(aabbs, 2):
                ivol = self._aabb_intersection_volume(a, b)
                if ivol > 0.0:
                    self._preflight_add_issue(
                        report,
                        'warning',
                        'possible_overlap_aabb',
                        (
                            f"Possible overlap in {group_name}: '{a['pv_name']}' and '{b['pv_name']}' "
                            f"(AABB intersection ≈ {ivol:.3f} mm^3)."
                        ),
                        object_refs=[a['pv_id'], b['pv_id']],
                        hint='Run Geant4 overlap checks for exact confirmation.',
                    )
                    overlap_reports += 1
                    if overlap_reports >= max_overlap_reports:
                        self._preflight_add_issue(
                            report,
                            'info',
                            'overlap_report_truncated',
                            f"Overlap reporting truncated after {max_overlap_reports} findings.",
                        )
                        return self._preflight_finalize(report)

        return self._preflight_finalize(report)


    def _collect_preflight_scope_refs(self, scope_type, scope_name):
        if not scope_type or not scope_name:
            raise ValueError('Scope type and name are required for scoped preflight.')

        state = self.current_geometry_state
        if not state:
            raise ValueError('No geometry state is loaded.')

        scope_kind = str(scope_type).strip().lower()
        scope_name = str(scope_name).strip()

        scope_refs = set()
        visited_lvs = set()
        visited_assemblies = set()

        def add_ref(value):
            if value:
                scope_refs.add(str(value))

        def visit_assembly(asm_name):
            if not asm_name or asm_name in visited_assemblies:
                return
            visited_assemblies.add(asm_name)

            asm = state.assemblies.get(asm_name)
            if not asm:
                return

            add_ref(asm.name)
            add_ref(f"ASM:{asm.name}")

            for pv in asm.placements:
                add_ref(pv.id)
                add_ref(pv.name)
                placed_ref = str(getattr(pv, 'volume_ref', '') or '').strip()
                if placed_ref in state.logical_volumes:
                    visit_logical_volume(placed_ref)
                elif placed_ref in state.assemblies:
                    visit_assembly(placed_ref)

        def visit_logical_volume(lv_name):
            if not lv_name or lv_name in visited_lvs:
                return
            visited_lvs.add(lv_name)

            lv = state.logical_volumes.get(lv_name)
            if not lv:
                return

            add_ref(lv.name)
            add_ref(f"LV:{lv.name}")
            add_ref(lv.solid_ref)
            add_ref(lv.material_ref)

            if lv.content_type == 'physvol':
                for pv in lv.content or []:
                    add_ref(pv.id)
                    add_ref(pv.name)
                    placed_ref = str(getattr(pv, 'volume_ref', '') or '').strip()
                    if placed_ref in state.logical_volumes:
                        visit_logical_volume(placed_ref)
                    elif placed_ref in state.assemblies:
                        visit_assembly(placed_ref)
            else:
                proc = lv.content
                placed_ref = str(getattr(proc, 'volume_ref', '') or '').strip()
                if placed_ref in state.logical_volumes:
                    visit_logical_volume(placed_ref)
                elif placed_ref in state.assemblies:
                    visit_assembly(placed_ref)

        if scope_kind == 'logical_volume':
            if scope_name not in state.logical_volumes:
                raise ValueError(f"Logical volume '{scope_name}' not found.")
            visit_logical_volume(scope_name)
        elif scope_kind == 'assembly':
            if scope_name not in state.assemblies:
                raise ValueError(f"Assembly '{scope_name}' not found.")
            visit_assembly(scope_name)
        else:
            raise ValueError(f"Unsupported scope type '{scope_type}'.")

        if not scope_refs:
            raise ValueError('Scoped preflight could not resolve any objects for the provided scope.')

        return scope_refs

    def build_scoped_preflight_report(self, full_report, scope_type, scope_name):
        scope_refs = self._collect_preflight_scope_refs(scope_type, scope_name)
        filtered_issues = []
        for issue in full_report.get('issues', []):
            refs = issue.get('object_refs', [])
            if not isinstance(refs, list):
                refs = [refs]

            for ref in refs:
                if ref is None:
                    continue
                if str(ref) in scope_refs:
                    filtered_issues.append(issue)
                    break

        scoped_report = {
            'version': full_report.get('version', 1),
            'name': f"{full_report.get('name', 'geometry_preflight_v1')}_scope",
            'issues': list(filtered_issues),
        }
        return self._preflight_finalize(scoped_report)

    def generate_macro_file(self, job_id, sim_params, build_dir, run_dir, version_dir):
        """
        Generates a Geant4 macro file from simulation parameters.

        Args:
            job_id (str): A unique identifier for this simulation run.
            sim_params (dict): A dictionary containing settings from the frontend.
            build_dir (str): The path to the Geant4 build directory.
            run_dir (str): The path to the specific directory for this run's output.
            version_dir (str): The path to the directory of the project version being run.

        Returns:
            str: The path to the generated macro file.
        """
        # --- Save metadata ---
        raw_sim_params = dict(sim_params or {})
        metadata = {
            'job_id': job_id,
            'timestamp': datetime.now().isoformat(),
            'total_events': raw_sim_params.get('events', 1),
            'sim_options': raw_sim_params,
        }
        metadata_path = os.path.join(run_dir, "metadata.json")
        macro_path = os.path.join(run_dir, "run.mac")
        version_json_path = os.path.join(version_dir, "version.json")

        # 1. Load the geometry from the version.json file, not the current state
        try:
            with open(version_json_path, 'r') as f:
                state_dict = json.load(f)
            
            # The GDML writer needs a GeometryState object
            temp_state = GeometryState.from_dict(state_dict)
            resolved_run_manifest = self.resolve_saved_run_manifest(raw_sim_params, state=temp_state)
            scoring_runtime = build_scoring_runtime_plan(temp_state.scoring.to_dict())
            forced_run_manifest_overrides = {}
            if scoring_runtime.get('requires_hits') and not resolved_run_manifest.get('save_hits', False):
                resolved_run_manifest['save_hits'] = True
                forced_run_manifest_overrides['save_hits'] = True
            gdml_string = GDMLWriter(temp_state).get_gdml_string()
            metadata['total_events'] = resolved_run_manifest.get('events', 1)
            metadata['resolved_run_manifest'] = resolved_run_manifest
            metadata['environment'] = temp_state.environment.to_dict()
            metadata['environment_summary'] = temp_state.environment.to_summary_dict()
            metadata['scoring'] = temp_state.scoring.to_dict()
            metadata['scoring_summary'] = temp_state.scoring.to_summary_dict()
            metadata['scoring_runtime'] = {
                'schema_version': scoring_runtime.get('schema_version', 1),
                'supported_quantities': deepcopy(scoring_runtime.get('supported_quantities', [])),
                'artifact_request_count': int(scoring_runtime.get('artifact_request_count', 0)),
                'skipped_tally_count': int(scoring_runtime.get('skipped_tally_count', 0)),
                'requires_hits': bool(scoring_runtime.get('requires_hits')),
                'skipped_tallies': deepcopy(scoring_runtime.get('skipped_tallies', [])),
                'forced_run_manifest_overrides': forced_run_manifest_overrides,
            }
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            gdml_output_path = os.path.join(run_dir, "geometry.gdml")
            with open(gdml_output_path, 'w') as f:
                f.write(gdml_string)
        except Exception as e:
            raise RuntimeError(f"Failed to process geometry for simulation: {e}")

        # 2. Generate the macro content
        macro_content = []
        macro_content.append("# AirPet Auto-Generated Macro")
        macro_content.append(f"# Job ID: {job_id}")
        macro_content.append("")
        
        # Disable trajectory storage to prevent Visualization cleanup crashes
        macro_content.append("/tracking/storeTrajectory 0")
        
        # --- Set random seed ---
        macro_content.append("\n# --- Random Seed ---")
        seed1 = resolved_run_manifest.get('seed1', 0)
        seed2 = resolved_run_manifest.get('seed2', 0)
        macro_content.append("\n# --- Random Seed ---")
        if seed1 > 0 and seed2 > 0:
            macro_content.append(f"/random/setSeeds {seed1} {seed2}")
        else:
            macro_content.append("# Using default/random seeds")

        # --- Load Geometry ---
        macro_content.append(f"/g4pet/detector/readFile geometry.gdml")
        macro_content.append("")

        # --- Global Field Configuration ---
        global_magnetic_field = temp_state.environment.global_uniform_magnetic_field
        global_electric_field = temp_state.environment.global_uniform_electric_field

        macro_content.append("# --- Global Magnetic Field ---")
        if global_magnetic_field.enabled:
            vector = global_magnetic_field.field_vector_tesla
            macro_content.append(
                "/globalField/setValue "
                f"{float(vector['x']):.12g} "
                f"{float(vector['y']):.12g} "
                f"{float(vector['z']):.12g} tesla"
            )
        else:
            macro_content.append("# Global magnetic field is disabled.")
        macro_content.append("")

        macro_content.append("# --- Global Electric Field ---")
        if global_electric_field.enabled:
            vector = global_electric_field.field_vector_volt_per_meter
            macro_content.append(
                "/globalField/setElectricValue "
                f"{float(vector['x']):.12g} "
                f"{float(vector['y']):.12g} "
                f"{float(vector['z']):.12g} volt/m"
            )
        else:
            macro_content.append("# Global electric field is disabled.")
        macro_content.append("")

        local_magnetic_field = temp_state.environment.local_uniform_magnetic_field
        macro_content.append("# --- Local Magnetic Field Assignments ---")
        if local_magnetic_field.enabled and local_magnetic_field.target_volume_names:
            for volume_name in local_magnetic_field.target_volume_names:
                macro_content.append(
                    "/g4pet/detector/addLocalMagField "
                    f"{volume_name}|"
                    f"{float(local_magnetic_field.field_vector_tesla['x']):.12g}|"
                    f"{float(local_magnetic_field.field_vector_tesla['y']):.12g}|"
                    f"{float(local_magnetic_field.field_vector_tesla['z']):.12g}"
                )
        elif local_magnetic_field.enabled:
            macro_content.append("# Local magnetic field is enabled, but no target volumes were configured.")
        elif local_magnetic_field.target_volume_names:
            macro_content.append("# Local magnetic field assignment is disabled.")
        else:
            macro_content.append("# No local magnetic field assignments defined.")
        macro_content.append("")

        local_electric_field = temp_state.environment.local_uniform_electric_field
        macro_content.append("# --- Local Electric Field Assignments ---")
        if local_electric_field.enabled and local_electric_field.target_volume_names:
            for volume_name in local_electric_field.target_volume_names:
                macro_content.append(
                    "/g4pet/detector/addLocalElecField "
                    f"{volume_name}|"
                    f"{float(local_electric_field.field_vector_volt_per_meter['x']):.12g}|"
                    f"{float(local_electric_field.field_vector_volt_per_meter['y']):.12g}|"
                    f"{float(local_electric_field.field_vector_volt_per_meter['z']):.12g}"
                )
        elif local_electric_field.enabled:
            macro_content.append("# Local electric field is enabled, but no target volumes were configured.")
        elif local_electric_field.target_volume_names:
            macro_content.append("# Local electric field assignment is disabled.")
        else:
            macro_content.append("# No local electric field assignments defined.")
        macro_content.append("")

        region_controls = temp_state.environment.region_cuts_and_limits
        macro_content.append("# --- Region Cuts And Limits ---")
        if region_controls.enabled and region_controls.target_volume_names:
            macro_content.append(
                "/g4pet/detector/addRegionCutsAndLimits "
                f"{region_controls.region_name}|"
                f"{','.join(region_controls.target_volume_names)}|"
                f"{float(region_controls.production_cut_mm):.12g}|"
                f"{float(region_controls.max_step_mm):.12g}|"
                f"{float(region_controls.max_track_length_mm):.12g}|"
                f"{float(region_controls.max_time_ns):.12g}|"
                f"{float(region_controls.min_kinetic_energy_mev):.12g}|"
                f"{float(region_controls.min_range_mm):.12g}"
            )
        elif region_controls.enabled:
            macro_content.append("# Region cuts and limits are enabled, but no target volumes were configured.")
        elif region_controls.target_volume_names:
            macro_content.append("# Region cuts and limits are disabled.")
        else:
            macro_content.append("# No region cuts and limits defined.")
        macro_content.append("")

        # --- Configure Sensitive Detectors ---
        macro_content.append("# --- Sensitive Detectors ---")
        sensitive_lvs = [lv for lv in self.current_geometry_state.logical_volumes.values() if lv.is_sensitive]

        if not sensitive_lvs:
            macro_content.append("# No sensitive detectors defined.")
        else:
            for lv in sensitive_lvs:
                sd_name = f"{lv.name}_SD"
                macro_content.append(f"/g4pet/detector/addSD {lv.name} {sd_name}")

        macro_content.append("")

        # --- Initialize ---
        macro_content.append("/run/initialize")
        macro_content.append("")

        # --- Add production cuts ---
        macro_content.append("# --- Physics Cuts for Performance ---")
        production_cut = str(resolved_run_manifest.get('production_cut') or '1.0 mm').strip()
        macro_content.append(f"/run/setCut {production_cut}")
        macro_content.append("")

        # --- Add commands to control n-tuple saving ---
        macro_content.append("# --- N-tuple Saving Control ---")
        save_particles = resolved_run_manifest.get('save_particles', False)
        save_hits = resolved_run_manifest.get('save_hits', True)
        save_hit_metadata = resolved_run_manifest.get('save_hit_metadata', True)
        macro_content.append(f"/g4pet/run/saveParticles {str(save_particles).lower()}")
        macro_content.append(f"/g4pet/run/saveHits {str(save_hits).lower()}")
        macro_content.append(f"/g4pet/run/saveHitMetadata {str(save_hit_metadata).lower()}")
        
        # Keep the default low enough that low-energy studies still produce hits.
        hit_threshold = str(resolved_run_manifest.get('hit_energy_threshold') or '1 eV').strip()
        macro_content.append(f"/g4pet/run/hitEnergyThreshold {hit_threshold}")
        macro_content.append("")

        # --- ADD VERBOSITY FOR DEBUGGING ---
        macro_content.append("# --- Verbosity Settings ---")
        #macro_content.append("/tracking/verbose 1") # Print a message for every new track
        #macro_content.append("/hits/verbose 2")     # Print every single hit as it's processed
        macro_content.append("")

        # --- Configure Source (using GPS) ---
        active_ids = self.current_geometry_state.active_source_ids
        active_sources = []
        
        # Collect source objects
        for s_id in active_ids:
            for source in self.current_geometry_state.sources.values():
                if source.id == s_id:
                    active_sources.append(source)
                    break
        
        if not active_sources:
            macro_content.append("# WARNING: No active particle source was specified for this run.")
        else:
            # 1. Calculate Total Activity for Normalization
            total_activity = sum([float(s.activity) for s in active_sources])
            if total_activity == 0: total_activity = 1.0 # Prevent division by zero

            macro_content.append("# --- Primary Particle Source(s) ---")
            
            for i, source in enumerate(active_sources):
                # Calculate relative intensity (0.0 to 1.0)
                relative_intensity = float(source.activity) / total_activity
                
                if i == 0:
                    # First source defines the GPS list
                    macro_content.append(f"/gps/source/intensity {relative_intensity}")
                else:
                    # Subsequent sources are added
                    macro_content.append(f"/gps/source/add {relative_intensity}")

                macro_content.append(f"# Source: {source.name} (Activity: {source.activity} Bq)")
                
                cmds = source.gps_commands.copy()
                direction_vector = str(cmds.pop('ang/dir1', '') or '').strip()
                ang_type = str(cmds.get('ang/type', '') or '').strip().lower()
                emit_gps_direction = bool(direction_vector) and ang_type in {'beam1d', 'direction', 'directed', 'beam'}
                if emit_gps_direction:
                    cmds.pop('ang/type', None)
                
                # Handling Confinement and Transform
                evaluated_pos = source._evaluated_position
                evaluated_rot = source._evaluated_rotation
                
                if source.confine_to_pv:
                    macro_content.append(f"/gps/pos/confine {source.confine_to_pv}")
                
                # Map Box to Para if needed (for Volume sources)
                # Note: The source shape parameters (halfx, radius, etc.) are already set correctly 
                # (with margins) by add_source/update_particle_source, so we trust them.
                if cmds.get('pos/type') == 'Volume' and cmds.get('pos/shape') == 'Box':
                     cmds['pos/shape'] = 'Para'

                # Write GPS commands
                for cmd, value in cmds.items():
                    if cmd == 'pos/confine': continue # Already handled or skipped if logic dictates
                    
                    # Evaluate the expression to resolve defines/math
                    success, val = self.expression_evaluator.evaluate(str(value), verbose=False)
                    final_val_str = str(value)

                    if success and isinstance(val, (int, float)):
                        # Append Unit based on command type (Heuristics)
                        # Energy -> keV
                        if 'ene/' in cmd or 'energy' in cmd:
                            final_val_str = f"{val} keV"
                        
                        # Time -> s (internal time unit)
                        elif 'time/' in cmd:
                            final_val_str = f"{val} s"
                            
                        # Length -> mm (internal length unit)
                        # Check for length-like keywords in pos/
                        elif 'radius' in cmd or 'half' in cmd or 'centre' in cmd:
                            final_val_str = f"{val} mm"
                        elif 'pos/' in cmd and ('sigma_r' in cmd or 'sigma_x' in cmd or 'sigma_y' in cmd):
                            # pos/sigma is length
                            final_val_str = f"{val} mm"

                        # Angle -> rad
                        elif 'ang/' in cmd:
                            # exclusion: rot1/rot2 are unitless vectors
                            if 'rot' not in cmd:
                                final_val_str = f"{val} rad"
                            else:
                                final_val_str = f"{val}"
                                
                        elif 'pos/' in cmd and ('alpha' in cmd or 'theta' in cmd or 'phi' in cmd):
                             # para parameters are angles
                            final_val_str = f"{val} rad"
                            
                        else:
                            # Default: just the number
                            final_val_str = f"{val}"

                    macro_content.append(f"/gps/{cmd} {final_val_str}")

                if emit_gps_direction:
                    raw_components = direction_vector.replace(',', ' ').split()
                    formatted_components = []
                    for component in raw_components[:3]:
                        success, val = self.expression_evaluator.evaluate(str(component), verbose=False)
                        if success and isinstance(val, (int, float)):
                            formatted_components.append(f"{float(val):.8g}")
                        else:
                            formatted_components.append(str(component))
                    if len(formatted_components) == 3:
                        try:
                            dx, dy, dz = (float(formatted_components[0]), float(formatted_components[1]), float(formatted_components[2]))
                            norm = np.linalg.norm([dx, dy, dz])
                            if norm <= 1e-12:
                                macro_content.append("/gps/direction 0 0 1")
                            else:
                                macro_content.append(f"/gps/direction {dx / norm:.8g} {dy / norm:.8g} {dz / norm:.8g}")
                        except Exception:
                            macro_content.append(f"/gps/direction {' '.join(formatted_components)}")
                    else:
                        macro_content.append(f"/gps/direction {direction_vector}")
	                
	                # Write Position (Centre)
                # Use evaluated_pos (either Source origin or PV origin)
                pos = evaluated_pos
                macro_content.append(f"/gps/pos/centre {pos['x']} {pos['y']} {pos['z']} mm")

                # Write Rotation
                # Use evaluated_rot (either Source rot or PV rot)
                rot = evaluated_rot
                r = R.from_euler('zyx', [rot['z'], rot['y'], rot['x']], degrees=False)
                rot_matrix = r.as_matrix()
                x_prime = rot_matrix[:, 0]
                y_prime = rot_matrix[:, 1]
                macro_content.append(f"/gps/ang/rot1 {x_prime[0]} {x_prime[1]} {x_prime[2]}")
                macro_content.append(f"/gps/ang/rot2 {y_prime[0]} {y_prime[1]} {y_prime[2]}")
                
                macro_content.append("")

        # --- Add Track Saving Logic ---
        macro_content.append("\n# --- Output and Visualization ---")
        tracks_dir = os.path.join(run_dir, "tracks")
        os.makedirs(tracks_dir, exist_ok=True)
        macro_content.append(f"/g4pet/event/printTracksToDir tracks/")
        
        save_range_str = raw_sim_params.get('save_tracks_range', '0-0')
        try:
            if '-' in save_range_str:
                start_event, end_event = map(int, save_range_str.split('-'))
            else:
                start_event = end_event = int(save_range_str)
        except (ValueError, IndexError):
            start_event, end_event = 0, 0 # Default on error
        macro_content.append(f"/g4pet/event/setTrackEventRange {start_event} {end_event}")
        
        # Set the output HDF5 file name
        macro_content.append(f"/analysis/setFileName output.hdf5")

        # --- Add the print progress command ---
        print_progress = resolved_run_manifest.get('print_progress', 0)
        if print_progress > 0:
            macro_content.append(f"/run/printProgress {print_progress}")

        # --- Run Beam On ---
        num_events = resolved_run_manifest.get('events', 1)
        macro_content.append("\n# --- Start Simulation ---")
        macro_content.append(f"/run/beamOn {num_events}")

        # 3. Write the macro file
        with open(macro_path, 'w') as f:
            f.write("\n".join(macro_content))

        metadata['run_manifest_summary'] = build_run_manifest_summary(
            metadata,
            run_dir,
            version_id=os.path.basename(os.path.normpath(version_dir)) or None,
        )
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        return macro_path
