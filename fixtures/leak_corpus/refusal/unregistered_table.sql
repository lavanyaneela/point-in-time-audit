SELECT p.entity_id, m.score
FROM predictions AS p
JOIN mystery_scores AS m
  ON m.entity_id = p.entity_id
