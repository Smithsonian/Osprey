#Postgres function to update the column last_update on files when the row is updated
CREATE FUNCTION updated_at_files() RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.last_update := NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trigger_updated_at_files
  BEFORE UPDATE ON files
  FOR EACH ROW
  EXECUTE PROCEDURE updated_at_files();