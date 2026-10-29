-- Both conditions at once. The named leak wins the exit code; the refusal is still printed.
SELECT p.entity_id, COUNT(*) AS n, MAX(c.updated_at) AS last_touch
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
JOIN crm_accounts AS c
  ON c.entity_id = p.entity_id
GROUP BY p.entity_id
