-- BETWEEN establishes arrival at or before prediction, so this join is
-- knowability correct; the analyzer still declines to certify a predicate
-- it cannot read as a bare comparison, and E3 prices the flag as cost.
SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
WHERE e.arrival_time BETWEEN p.prediction_time - INTERVAL 365 DAY AND p.prediction_time
  AND e.fact_time <= p.prediction_time
GROUP BY p.entity_id
