-- The panel is EUNE only, and the region never did any work: account-v1 and
-- match-v5 both route through the regional host, where eun1 and euw1 are the
-- same `europe` (r3m.riot_api.PLATFORM_REGION). The comparison pass needs a
-- puuid and a match list, nothing platform-specific.
--
-- What it held was not trustworthy either. The frontend defaulted the select
-- to euw1, so a stored euw1 cannot be told apart from a tester who never
-- touched it. Three rows carried a value when this ran.

alter table quiz_session drop column riot_region;
