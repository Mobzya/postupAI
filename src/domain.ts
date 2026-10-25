export const TRACKS = [
  'general_budget', 'special_quota', 'separate_quota', 'targeted',
  'bvi', 'paid', 'grant', 'special_selection',
] as const;
export type Track = typeof TRACKS[number];
export type Distribution = ReadonlyArray<{ score: number; probability: number }>;

export function validateDistribution(distribution: Distribution, maximum = 100): void {
  if (!Number.isFinite(maximum) || maximum <= 0 || distribution.length === 0) {
    throw new Error('invalid_distribution');
  }
  let total = 0;
  const seen = new Set<number>();
  for (const point of distribution) {
    if (!Number.isFinite(point.score) || point.score < 0 || point.score > maximum ||
        seen.has(point.score) || !Number.isFinite(point.probability) ||
        point.probability < 0 || point.probability > 1) {
      throw new Error('invalid_distribution');
    }
    seen.add(point.score);
    total += point.probability;
  }
  if (Math.abs(total - 1) > 1e-9) throw new Error('unnormalized_distribution');
}

export interface ExamOption { key: string; minimum: number; maximum: number }
export interface ScoreRules {
  track: Track;
  verified: boolean;
  slots: ReadonlyArray<ReadonlyArray<ExamOption>>;
  achievementCap: number;
}

export type ScoreResult =
  | { status: 'ok'; total: number; selected: string[]; achievementPoints: number }
  | { status: 'insufficient_data' | 'ineligible' | 'unsupported_track'; reason: string };

// Foundation contract only: no real university rules or automatic olympiad rights.
export function competitionScore(
  scores: Readonly<Record<string, number>>,
  verifiedAchievementPoints: number,
  rules: ScoreRules,
): ScoreResult {
  if (!rules.verified) return { status: 'insufficient_data', reason: 'unverified_rules' };
  if (rules.track !== 'general_budget' && rules.track !== 'paid') {
    return { status: 'unsupported_track', reason: 'requires_separate_rules' };
  }
  if (!rules.slots.length || !Number.isFinite(rules.achievementCap) || rules.achievementCap < 0 ||
      !Number.isFinite(verifiedAchievementPoints) || verifiedAchievementPoints < 0) {
    throw new Error('invalid_rules_or_achievements');
  }
  const allKeys = new Set<string>();
  for (const slot of rules.slots) {
    if (!slot.length) throw new Error('empty_exam_slot');
    for (const option of slot) {
      if (!option.key || allKeys.has(option.key) || !Number.isFinite(option.minimum) ||
          !Number.isFinite(option.maximum) || option.minimum < 0 ||
          option.maximum <= 0 || option.minimum > option.maximum) throw new Error('invalid_exam_rule');
      allKeys.add(option.key);
    }
  }
  const selected: string[] = [];
  let total = 0;
  for (const slot of rules.slots) {
    const provided = slot.filter(option => scores[option.key] !== undefined);
    if (!provided.length) return { status: 'insufficient_data', reason: 'missing_exam' };
    for (const option of provided) {
      const score = scores[option.key]!;
      if (!Number.isFinite(score) || score < 0 || score > option.maximum) throw new Error('invalid_exam_score');
    }
    const valid = provided.filter(option => scores[option.key]! >= option.minimum);
    if (!valid.length) return provided.length < slot.length
      ? { status: 'insufficient_data', reason: 'missing_alternative_exam' }
      : { status: 'ineligible', reason: 'below_minimum' };
    valid.sort((a, b) => scores[b.key]! - scores[a.key]! || a.key.localeCompare(b.key));
    const chosen = valid[0]!;
    selected.push(chosen.key);
    total += scores[chosen.key]!;
  }
  const achievementPoints = Math.min(verifiedAchievementPoints, rules.achievementCap);
  return { status: 'ok', total: total + achievementPoints, selected, achievementPoints };
}

export function forecastAvailability(): { status: 'insufficient_data'; reason: string } {
  return { status: 'insufficient_data', reason: 'missing_confirmed_competition_populations_and_calibration' };
}
