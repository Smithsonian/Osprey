
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



create_lot <- function(db){
  
  lotinfo_q <- dbSendQuery(db, "SELECT * FROM qc_settings WHERE project_id = ?")
  dbBind(lotinfo_q, list(project_id))
  proj_settings <- dbFetch(lotinfo_q)
  dbClearResult(lotinfo_q)
  
  lotinfo_q <- dbSendQuery(db, "INSERT INTO qc_lots (project_id) VALUES (?) RETURNING qc_lot_id")
  dbBind(lotinfo_q, list(project_id))
  next_lot <- dbFetch(lotinfo_q)
  dbClearResult(lotinfo_q)
  
  lotinfo_q <- dbSendQuery(db, "SELECT qc_lot_id FROM qc_lots WHERE qc_pass IS NOT NULL AND project_id = ? ORDER BY qc_lot_id DESC LIMIT 1")
  dbBind(lotinfo_q, list(project_id))
  lot_id <- dbFetch(lotinfo_q)[1,1]
  dbClearResult(lotinfo_q)
  
  lotinfo_q <- dbSendQuery(db, "SELECT max(lots_dates)::text from (select unnest(qc_lot_dates) as lots_dates FROM qc_lots WHERE qc_lot_id = ?) a")
  dbBind(lotinfo_q, list(lot_id))
  lot_date <- dbFetch(lotinfo_q)
  dbClearResult(lotinfo_q)
  
  lotinfo_q <- dbSendQuery(db, "SELECT qc_pass, qc_level FROM qc_lots WHERE qc_pass IS NOT NULL AND project_id = ? ORDER BY qc_lot_id DESC LIMIT 5")
  dbBind(lotinfo_q, list(project_id))
  lots <- dbFetch(lotinfo_q)
  dbClearResult(lotinfo_q)
  
  lotinfo_q <- dbSendQuery(db, "SELECT COUNT(*) FROM (SELECT qc_pass FROM qc_lots WHERE qc_pass IS NOT NULL AND project_id = ? ORDER BY qc_lot_id DESC LIMIT 5) a WHERE qc_pass = 't'")
  dbBind(lotinfo_q, list(project_id))
  lots_pass <- dbFetch(lotinfo_q)
  dbClearResult(lotinfo_q)
  
  lotinfo_q <- dbSendQuery(db, "SELECT COUNT(*) FROM (SELECT qc_pass FROM qc_lots WHERE qc_pass IS NOT NULL AND project_id = ? ORDER BY qc_lot_id DESC LIMIT 5) a WHERE qc_pass = 'f'")
  dbBind(lotinfo_q, list(project_id))
  lots_fail <- dbFetch(lotinfo_q)
  dbClearResult(lotinfo_q)
  
  if(dim(lots)[1] < 6){
    next_lot_level <- "Normal"
    next_lot_percent <- proj_settings$qc_normal_percent
    next_lot_days <- 2
  }else{
    if (lot_info$qc_level == "Normal"){
      if (lots_pass == 5){
        next_lot_level <- "Reduced"
        next_lot_percent <- proj_settings$qc_reduced_percent
        next_lot_days <- 5
      }else if (lots_fail > 1){
        next_lot_level <- "Tightened"
        next_lot_percent <- proj_settings$qc_tightened_percent
        next_lot_days <- 1
      }
    }else if (lot_info$qc_level == "Reduced"){
      if (lots_pass == 5){
        next_lot_level <- "Reduced"
        next_lot_percent <- proj_settings$qc_reduced_percent
        next_lot_days <- 5
      }else if (lots_fail > 1){
        next_lot_level <- "Normal"
        next_lot_percent <- proj_settings$qc_normal_percent
        next_lot_days <- 2
      }
    }else if (lot_info$qc_level == "Tightened"){
      if (lots_pass == 5){
        next_lot_level <- "Normal"
        next_lot_percent <- proj_settings$qc_normal_percent
        next_lot_days <- 2
      }else{
        next_lot_level <- "Tightened"
        next_lot_percent <- proj_settings$qc_tightened_percent
        next_lot_days <- 1
      }
    }
  }
  
  lotinfo_q <- paste0("SELECT date::text FROM folders WHERE date > '", lot_date, "'::date AND project_id = ", project_id, " GROUP BY date ORDER BY date LIMIT ", next_lot_days)
  next_dates <- dbGetQuery(db, lotinfo_q)
  
  #There are enough days for next lot
  if (dim(next_dates)[1] >= next_lot_days){
    update_q <- paste0("UPDATE qc_lots SET qc_lot_title = 'Lot ", next_lot, "', qc_lot_percent = ", next_lot_percent, ", qc_level = '", next_lot_level, "', qc_lot_dates = cast(string_to_array('", paste(next_dates[,1], collapse = ","),"', ',') as date[]) WHERE qc_lot_id = ", next_lot)
    c <- dbSendQuery(db, update_q)
    dbClearResult(c)
    return(next_lot)
  }
  return(0)
}

