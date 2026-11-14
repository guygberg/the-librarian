-- A Suggestion, its run and its Evidence belong to one Workspace: no cross-workspace references.
CREATE TRIGGER suggestions_same_workspace_run BEFORE INSERT ON suggestions
WHEN NEW.workspace IS NOT (SELECT workspace FROM extraction_runs WHERE id = NEW.run_id)
BEGIN SELECT RAISE(ABORT, 'a suggestion and its run must share a workspace'); END;

CREATE TRIGGER suggestion_evidence_same_workspace BEFORE INSERT ON suggestion_evidence
WHEN NEW.workspace IS NOT (SELECT workspace FROM suggestions WHERE id = NEW.suggestion_id)
  OR NEW.workspace IS NOT (SELECT workspace FROM source_item_revisions WHERE id = NEW.revision_id)
BEGIN SELECT RAISE(ABORT, 'suggestion evidence must share its suggestion and revision workspace'); END;

CREATE TRIGGER suggestion_events_same_workspace BEFORE INSERT ON suggestion_events
WHEN NEW.workspace IS NOT (SELECT workspace FROM suggestions WHERE id = NEW.suggestion_id)
BEGIN SELECT RAISE(ABORT, 'a suggestion event must share its suggestion workspace'); END;
