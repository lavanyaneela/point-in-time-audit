-- One mutable timestamp. Whether any value was knowable is unrepresentable.
SELECT p.entity_id, c.updated_at
FROM predictions AS p
JOIN crm_accounts AS c
  ON c.entity_id = p.entity_id
 AND c.updated_at <= p.prediction_time
