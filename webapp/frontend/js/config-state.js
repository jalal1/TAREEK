/* Complete engine configuration; paths are arrays so dotted MATSim keys stay literal. */
class ConfigurationState {
  constructor() {
    this.config = null; this.original = null; this.listeners = new Set();
    this.surveyCache = {}; this.surveyPositions = {};
  }
  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  notify(path, source) { for (const listener of this.listeners) listener({path, source}); }
  load(config) {
    this.config = structuredClone(config);
    this.original = structuredClone(config);
    this.surveyCache = {};
    this.surveyPositions = {};
    this.notify([], 'load');
  }
  get(path) { return path.reduce((value, key) => value?.[key], this.config); }
  set(path, value, source = 'wizard') {
    if (!this.config) throw new Error('Choose a starting configuration first.');
    if (!path.length || path.some(key => ['__proto__', 'prototype', 'constructor'].includes(String(key)))) {
      throw new Error('This configuration path is preserved but cannot be edited safely.');
    }
    let target = this.config;
    path.slice(0, -1).forEach(key => { target = target[key] ??= {}; });
    target[path.at(-1)] = structuredClone(value);
    this.notify(path, source);
  }
  snapshot() { return structuredClone(this.config); }
  surveyIndex(custom) {
    const surveys = this.config?.data?.surveys;
    return Array.isArray(surveys) ? surveys.findIndex(s => s && typeof s === 'object' &&
      (custom ? s.type !== 'nhts' : s.type === 'nhts')) : -1;
  }
  survey(custom) { return this.config?.data?.surveys?.[this.surveyIndex(custom)]; }
  includeSurvey(custom, include) {
    if (!Array.isArray(this.config?.data?.surveys)) return;
    const index = this.surveyIndex(custom);
    if (include && index < 0) {
      const entry = this.surveyCache[custom];
      if (!entry) return; // New sources require an explicit template, never guessed paths.
      const position = this.surveyPositions[custom] ?? this.config.data.surveys.length;
      this.config.data.surveys.splice(position, 0, structuredClone(entry));
    } else if (!include && index >= 0) {
      this.surveyPositions[custom] = index;
      this.surveyCache[custom] = this.config.data.surveys.splice(index, 1)[0];
    }
    this.notify(['data', 'surveys'], 'wizard');
  }
}

const CONFIG_BINDINGS = {
  'mode-car-survey_rate': ['modes', 'car', 'survey_rate'],
  'mode-car-share_adj': ['modes', 'car', 'share_adjustment'],
  'modeChoice-fallback': ['mode_choice', 'fallback_mode'],
  'modeChoice-chainConsistency': ['mode_choice', 'chain_consistency'],
  'transit-enabled': ['matsim', 'transit_network'],
  'gtfs-catalog_max_age': ['gtfs', 'catalog_max_age_days'],
  'gtfs-feed_max_age': ['gtfs', 'feed_max_age_days'],
  'gtfs-sample_day': ['matsim', 'gtfs_sample_day'],
  'demand-scaling_factor': ['plan_generation', 'scaling_factor'],
  'demand-random_seed': ['plan_generation', 'random_seed'],
  'demand-work_scaling_mult': ['plan_generation', 'work_scaling_multiplier'],
  // Computer resources: checked against this computer by updateResourceHints().
  'demand-num_processes': ['plan_generation', 'num_processes'],
  'pt2m-numOfThreads': ['matsim', 'pt2matsim', 'numOfThreads'],
  'sim-heap_size_gb': ['matsim', 'heap_size_gb'],
  'sim-network_heap_size_gb': ['matsim', 'network_heap_size_gb'],
  'sim-heap_ram_fraction': ['matsim', 'heap_ram_fraction'],
  'sim-global_threads': ['matsim', 'configurable_params', 'global.numberOfThreads'],
  'sim-qsim_threads': ['matsim', 'configurable_params', 'qsim.numberOfThreads'],
  'chain-min_length': ['chains', 'min_length'],
  'chain-max_work': ['chains', 'max_work_activities'],
  'nonwork-trip_share': ['nonwork_purposes', 'nonwork_trip_share'],
  'time-departure_jitter': ['duration_constraints', 'departure_jitter_minutes'],
  'time-trim_jitter': ['duration_constraints', 'trim_jitter_minutes'],
  'time-max_travel_buffer': ['duration_constraints', 'max_travel_buffer_minutes'],
  'poi-initial_radius': ['poi_assignment', 'initial_radius_m'],
  'poi-radius_increment': ['poi_assignment', 'radius_increment_m'],
  'poi-max_retries': ['poi_assignment', 'max_poi_retries'],
  'counts-enabled': ['counts', 'enabled'],
  'counts-fha_year': ['counts', 'fha', 'year'],
  'counts-fha_month': ['counts', 'fha', 'month'],
  'counts-fha_weight': ['counts', 'fha', 'weight'],
  'eval-run': ['evaluation', 'run_evaluation'],
  'eval-spatial_maps': ['evaluation', 'generate_spatial_maps'],
  'eval-per_device': ['evaluation', 'generate_per_device_reports'],
  'purpose-shopping-poi-has_name': ['nonwork_purposes', 'Shopping', 'poi_weighting', 'has_name'],
};
for (const mode of ['car', 'bus', 'rail', 'walk', 'bike']) {
  CONFIG_BINDINGS[`modeEnable-${mode}`] = ['modes', mode, 'enabled'];
  if (['bus', 'rail'].includes(mode)) {
    for (const key of ['config_rate', 'blend_weight']) CONFIG_BINDINGS[`mode-${mode}-${key}`] = ['modes', mode, key];
    CONFIG_BINDINGS[`mode-${mode}-access_buffer`] = ['modes', mode, 'availability', 'access_buffer_meters'];
  }
  if (['walk', 'bike'].includes(mode)) CONFIG_BINDINGS[`mode-${mode}-max_distance`] = ['modes', mode, 'availability', 'max_distance_meters'];
}
for (const key of ['maxLinkCandidateDistance', 'maxTravelCostFactor', 'nLinkThreshold', 'candidateDistanceMultiplier', 'travelCostType']) {
  CONFIG_BINDINGS[`pt2m-${key}`] = ['matsim', 'pt2matsim', key];
}
for (const [id, key] of Object.entries({iterations: 'lastIteration', linkstats_avg: 'linkStats.averageLinkStatsOverIterations', flow_capacity: 'qsim.flowCapacityFactor', storage_capacity: 'qsim.storageCapacityFactor'})) {
  CONFIG_BINDINGS[`sim-${id}`] = ['matsim', 'configurable_params', key];
}
for (const purpose of ['Shopping', 'School', 'Social', 'Dining', 'Other']) {
  const id = purpose.toLowerCase();
  CONFIG_BINDINGS[`purpose-${id}-enabled`] = ['nonwork_purposes', purpose, 'enabled'];
  for (const key of ['config_rate', 'blend_weight']) CONFIG_BINDINGS[`purpose-${id}-${key}`] = ['nonwork_purposes', purpose, 'trip_generation', key];
  CONFIG_BINDINGS[`purpose-${id}-od_beta`] = ['nonwork_purposes', purpose, 'od_matrix', 'beta'];
}
for (const activity of ['Work', 'School', 'Shopping', 'Escort', 'Dining', 'Social', 'Other']) {
  for (const [id, key] of Object.entries({min: 'min_minutes', max: 'max_minutes', priority: 'trim_priority'})) {
    CONFIG_BINDINGS[`dur-${activity}-${id}`] = ['duration_constraints', 'activity_durations', activity, key];
  }
}

if (typeof module !== 'undefined') module.exports = {ConfigurationState, CONFIG_BINDINGS};
