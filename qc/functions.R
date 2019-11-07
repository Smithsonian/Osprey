
add_files_to_lot <- function(lot_id, db){
  lotinfo_q <- paste0("SELECT qc_lot_percent, qc_lot_dates FROM qc_lots WHERE qc_lot_id = ", lot_id)
  flog.info(paste0("lotinfo_q: ", lotinfo_q), name = "qc")
  lotinfo <- dbGetQuery(db, lotinfo_q)
  
  qc_files_q <- paste0("SELECT count(*) as no_files FROM files WHERE folder_id IN (SELECT folder_id FROM folders WHERE date = ANY('", lotinfo$qc_lot_dates, "') AND project_id = ", project_id, ")")
  flog.info(paste0("qc_files_q: ", qc_files_q), name = "qc")
  qc_files <- dbGetQuery(db, qc_files_q)
  
  qc_limit <- ceiling(as.integer(qc_files$no_files) * (as.integer(lotinfo$qc_lot_percent)/100))
  
  qc_q <- paste0("INSERT INTO qc_lots_files (qc_lot_id, file_id) (SELECT ", lot_id, ", file_id FROM files WHERE folder_id IN (SELECT folder_id FROM folders WHERE date = ANY('", lotinfo$qc_lot_dates, "') AND project_id = ", project_id, ") ORDER BY RANDOM() LIMIT ", qc_limit, ")")
  flog.info(paste0("qc_q: ", qc_q), name = "qc")
  n <- dbSendQuery(db, qc_q)
  dbClearResult(n)
  
  return(TRUE)
}

