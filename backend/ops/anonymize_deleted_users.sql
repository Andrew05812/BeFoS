-- One-off backfill: bring accounts deleted before the erasure in
-- safety_service.delete_account to the same promise they were given when they tapped
-- «Удалить аккаунт». Run it against a copy first (docs/OPERATIONS.md §2--§3), and take a
-- dump before the real run: this deletes rows a user cannot re-create.
--
-- What it does NOT touch: the users row (soft delete keeps it on purpose), and reports,
-- which must outlive the account they describe so that deleting cannot erase a complaint.

begin;

-- The questionnaire, the score built from it, the vector built from the score.
delete from test_answers ta using users u where u.is_deleted and ta.user_id = u.id;
delete from test_results tr using users u where u.is_deleted and tr.user_id = u.id;
delete from compatibility_profiles cp using users u where u.is_deleted and cp.user_id = u.id;

-- The portrait's remaining details, and the record of whom this person was shown.
delete from activity_preferences ap using users u where u.is_deleted and ap.user_id = u.id;
delete from discovery_queue dq using users u where u.is_deleted and dq.viewer_id = u.id;

-- Edges. A match whose participant is gone is not a pair: the survivor's chat would still
-- accept messages to a person who no longer exists. Messages, read receipts and their
-- recommendations go with the match through the schema's own cascade.
delete from matches m
  using users u
  where u.is_deleted and (m.user_a_id = u.id or m.user_b_id = u.id);
delete from likes l
  using users u
  where u.is_deleted and (l.from_user_id = u.id or l.to_user_id = u.id);
delete from passes p
  using users u
  where u.is_deleted and (p.from_user_id = u.id or p.to_user_id = u.id);
delete from blocks b
  using users u
  where u.is_deleted and (b.blocker_id = u.id or b.blocked_id = u.id);

update profiles p
  set name = 'Deleted User',
      about = null,
      city = '',
      lifestyle = '{}'::jsonb,
      birth_date = date '1900-01-01',
      gender = 'erased',
      dating_goal = 'erased',
      age_min = 18,
      age_max = 18,
      gender_preference = '{}'::character varying[],
      city_preference = null,
      is_hidden = true
  from users u
  where u.is_deleted and p.user_id = u.id;

-- Interests hang off the profile, not the user.
delete from user_interests ui
  using profiles p join users u on u.id = p.user_id
  where u.is_deleted and ui.profile_id = p.id;

-- Photos are rows plus files, and this script cannot see the volume: verify the two sides
-- by name (docs/OPERATIONS.md §12) before deleting anything under /uploads.

commit;
