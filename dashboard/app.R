# Packages ----
library(shiny)
library(dplyr)
library(DBI)
library(DT)
library(futile.logger)
library(reshape)
library(stringr)
library(shinycssloaders)
library(shinydashboard)
library(shinyWidgets)
library(ggplot2)


# Settings ----
source("settings.R")
app_name <- "Osprey Dashboard"
app_ver <- "0.7.1"
github_link <- "https://github.com/Smithsonian/Osprey"

options(stringsAsFactors = FALSE)
options(encoding = 'UTF-8')

#Logfile----
dir.create("logs", showWarnings = FALSE)
logfile <- paste0("logs/", format(Sys.time(), "%Y%m%d_%H%M%S"), ".txt")
flog.logger("dashboard", INFO, appender=appender.file(logfile))


#Connect to the database ----
if (Sys.info()["nodename"] == "shiny.si.edu"){
  #For RHEL7 odbc driver
  pg_driver = "PostgreSQL"
}else{
  pg_driver = "PostgreSQL Unicode"
}

db <- dbConnect(odbc::odbc(),
                driver = pg_driver,
                database = pg_db,
                uid = pg_user,
                pwd = pg_pass,
                server = pg_host,
                port = 5432)

project <- dbGetQuery(db, paste0("SELECT * FROM projects WHERE project_id = ", project_id))
proj_name <- project$project_acronym

dbDisconnect(db)

site_title = paste0(proj_name)

# UI ----
ui <- dashboardPage(
  #header
  dashboardHeader(title = site_title),
  
  dashboardSidebar(disable = TRUE),
  #Body
  
  dashboardBody(
    
    fluidRow(
      shinycssloaders::withSpinner(valueBoxOutput("box_ok", width = 3)),
      shinycssloaders::withSpinner(valueBoxOutput("box_error", width = 3)),
      shinycssloaders::withSpinner(valueBoxOutput("itemcount", width = 3)),
      shinycssloaders::withSpinner(valueBoxOutput("totalbox", width = 3))
      ),
    fluidRow(
      column(width = 2,
             box(
               title = "Main", width = NULL, solidHeader = TRUE, status = "primary",
               uiOutput("projectmain")
             ),
             uiOutput("shares"),
             box(
               title = "Folders", width = NULL, solidHeader = TRUE, status = "primary",
               uiOutput("folderlist")
             )
        ),
      column(width = 8,
             uiOutput("project_alert"),
             box(
               title = "Folder details", width = NULL, solidHeader = TRUE, status = "primary",
               fluidRow(
                 column(width = 8,
                        uiOutput("folderinfo1")
                 ),
                 column(width = 4,
                        uiOutput("folderinfo2")
                 )
               ),
               hr(),
               uiOutput("tableheading"),
               uiOutput("filetable")
             )
      ),
      column(width = 2,
             box(
               title = "File details", width = NULL, solidHeader = TRUE, status = "primary",
               uiOutput("fileinfo")
             )
      )
    ),
    #Footer
    hr(),
    uiOutput("footer"),
    
    # #Refresh every 600 seconds
    if (project_active == TRUE){
      tags$head(HTML('<meta http-equiv="refresh" content="600">'))
    }
  )
)


# Server ----
server <- function(input, output, session) {
  #Connect to the database ----
  if (Sys.info()["nodename"] == "shiny.si.edu"){
    #For RHEL7 odbc driver
    pg_driver = "PostgreSQL"
  }else{
    pg_driver = "PostgreSQL Unicode"
  }
  
  db <- dbConnect(odbc::odbc(),
                  driver = pg_driver,
                  database = pg_db,
                  uid = pg_user,
                  pwd = pg_pass,
                  server = pg_host,
                  port = 5432)
  
  file_checks_q <- paste0("SELECT project_checks FROM projects WHERE project_id = ", project_id)
  flog.info(paste0("file_checks_q: ", file_checks_q), name = "dashboard")
  file_checks_list <<- dbGetQuery(db, file_checks_q)
  file_checks <- stringr::str_split(file_checks_list, ",")[[1]]
  
  check_count <- paste0("SELECT count(*) from files where folder_id IN (SELECT folder_id from folders WHERE project_id = ", project_id, ")")
  total_count <- dbGetQuery(db, check_count)
  
  if (str_detect(file_checks_list, 'old_name')){
    check_count <- paste0("SELECT count(file_name) from old_names where file_name NOT IN (SELECT file_name FROM files WHERE folder_id in (SELECT folder_id FROM folders WHERE project_id = ", project_id, ")) AND project_id = ", project_id, "")
    old_count <- dbGetQuery(db, check_count)
    total_count <- total_count + old_count
  }
  
  #err_count <- 0
  check_count <- paste0("SELECT count(distinct file_id) FROM file_checks WHERE check_results = 1 AND file_id in (SELECT file_id from files where folder_id IN (SELECT folder_id from folders WHERE project_id = ", project_id, "))")
  err_count <- dbGetQuery(db, check_count)[1]
  
  #box_error ----
  output$box_error <- renderValueBox({
    
    error_list_count <- err_count
    
    if (total_count == 0){
      err_files_count <- "NA"
      err_files_subtitle <- "Files with errors"
    }else{
      err_files_count <- paste0(round((error_list_count/total_count) * 100, 2), " %")
      
      if (error_list_count != total_count && err_files_count == "0 %"){
        err_files_count <- paste0(prettyNum(round((error_list_count/total_count) * 100, 5), big.mark = ",", scientific = FALSE), " %")
      }
      if (error_list_count != 0 && err_files_count == "0 %"){
        err_files_count <- paste0("> ", err_files_count)
      }
      err_files_subtitle <- paste0(prettyNum(error_list_count, big.mark = ",", scientific = FALSE), " files with errors")
    }
    
    valueBox(
      err_files_count, err_files_subtitle, icon = icon("exclamation-sign", lib = "glyphicon"),
      color = "red"
    )
  })
  
  
  #box_ok ----
  output$box_ok <- renderValueBox({

    ok_count <- paste0("WITH data AS 
                    (SELECT 
                      file_id, sum(check_results) as check_results 
                    FROM 
                      file_checks 
                    WHERE 
                      file_id in (SELECT 
                                file_id 
                              FROM files
                              WHERE folder_id IN 
                                (SELECT folder_id from folders WHERE project_id = ", project_id, ")) 
                                  GROUP BY file_id)
                  SELECT count(file_id) FROM data WHERE check_results = 0")
    ok_list_count <- dbGetQuery(db, ok_count)
    
    if (str_detect(file_checks_list, 'old_name')){
      ok_list_count <- ok_list_count + old_count
    }

    if (total_count == 0){
      ok_files_count <- "NA"
      ok_files_subtitle <- "Files OK"
    }else{
      ok_files_count <- paste0(round((ok_list_count/total_count) * 100, 2), " %")
      if (ok_list_count != total_count && ok_files_count == "100 %"){
        ok_files_count <- paste0(round((ok_list_count/total_count) * 100, 5), " %")
      }
      ok_files_subtitle <- paste0(prettyNum(ok_list_count, big.mark = ",", scientific = FALSE), " files OK")
    }
    
    valueBox(
      ok_files_count, ok_files_subtitle, icon = icon("ok-sign", lib = "glyphicon"),
      color = "green"
    )
  })
    
  
  #itemcount----
  output$itemcount <- renderValueBox({
    
    pending_count <- paste0("SELECT count(distinct file_id)
                        FROM file_checks 
                        WHERE check_results = 9 AND
                            file_id in (
                                SELECT file_id 
                                FROM files
                                WHERE folder_id IN (
                                        SELECT folder_id 
                                        FROM folders 
                                        WHERE project_id = ", project_id, "))")
    pending_files_count <- dbGetQuery(db, pending_count)

    if (dim(pending_files_count)[1] == 0){
      pending_files_count <- 0
    }
    
    valueBox(
      prettyNum(pending_files_count, big.mark = ",", scientific = FALSE), "Files Pending Verification", icon = icon("file", lib = "glyphicon"),
      color = "blue"
    )
  })
  
  
  #totalbox----
  output$totalbox <- renderValueBox({
    valueBox(
      prettyNum(total_count, big.mark = ",", scientific = FALSE), "No. of Images", icon = icon("picture", lib = "glyphicon"),
      color = "teal"
    )
  })
    
  
  
  output$filetable <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    req(which_folder != "NULL")
    
    postp_q <- paste0("SELECT project_postprocessing FROM projects WHERE project_id = ", project_id)
    flog.info(paste0("postp_q: ", postp_q), name = "dashboard")
    postprocess <- dbGetQuery(db, postp_q)
    
    if (is.na(postprocess)){
      DT::dataTableOutput("files_table")
    }else{
      tabsetPanel(
        tabPanel("Production", DT::dataTableOutput("files_table")),
        tabPanel("Post-Processing", DT::dataTableOutput("pp_table"))
      )
    }
  })
  
  
  #projectmain----
  output$projectmain <- renderUI({
    projectmain_html <- "<p><strong><a href=\"./\"><span class=\"glyphicon glyphicon-home\" aria-hidden=\"true\"></span> Home</a></strong></p>"
    #Only display if it is an active project, from settings
    if (project_active == TRUE){
      last_update_q <- paste0(
        "SELECT round(EXTRACT(epoch FROM NOW() - last_update)) AS last_update 
          FROM
            (SELECT updated_at AS last_update FROM folders WHERE project_id = ", project_id, "
            UNION
            SELECT updated_at AS last_update FROM files WHERE folder_id in (SELECT folder_id FROM folders WHERE project_id = ", project_id, ")
					ORDER BY last_update DESC LIMIT 1) a")
      
      flog.info(paste0("last_update_q: ", last_update_q), name = "dashboard")
      last_update <- as.numeric(dbGetQuery(db, last_update_q))
      
      if (!is.na(last_update)){
        if (last_update > 180){
          last_update_m <- ceiling(last_update / 60)
          if (last_update > 3600){
            last_update_text <- paste0("<p>Last update: ", last_update_m, " minutes ago <span class=\"label label-danger\" title=\"Is MDFilecheck running?\">Error</span></p>")
          }else{
            last_update_text <- paste0("<p>Last update: ", last_update_m, " minutes ago</p>")
          }
        }else{
          last_update_text <- paste0("<p>Last update: ", last_update, " seconds ago</p>")
        }
      }else{
        last_update_text <- ""
      }
    }else{
      last_update_text <- ""
    }
    
    #Not quite ready
    # if (project_active == TRUE){
    #   projectmain_html <- paste0(projectmain_html, last_update_text, "<p>", actionLink("dayprogress", label = "Progress during the day"), "<p>")
    # }
    
    #Disk used----
    filesize_q <- paste0("SELECT sum(filesize) as total_size FROM files_size WHERE file_id in (SELECT file_id FROM files WHERE folder_id IN (SELECT folder_id FROM folders WHERE project_id = ", project_id, "))")
    flog.info(paste0("filesize_q: ", filesize_q), name = "dashboard")
    total_size <- dbGetQuery(db, filesize_q)
    if (!is.na(total_size)){
      total_size_formatted <- utils:::format.object_size(total_size, "auto")
      projectmain_html <- paste0(projectmain_html, "<p>Total diskspace of files: ", total_size_formatted, "</p>")
    }
    
    HTML(projectmain_html)
  })
  
  
  
  #shares----
  output$shares <- renderUI({
    if (project_active != TRUE){
      req(FALSE)
    }
    
    shares_html <- ""
    
    shares_q <- paste0("SELECT * FROM projects_shares WHERE project_id = ", project_id)
    flog.info(paste0("shares_q: ", shares_q), name = "dashboard")
    shares <- dbGetQuery(db, shares_q)
    if (dim(shares)[1] > 0){
      for (i in seq(1, dim(shares)[1])){
        per_used <- round(as.numeric(shares$used[i]), 2)
        if (per_used > 90){
          prog_class <- "danger"
        }else if (per_used > 75){
          prog_class <- "warning"
        }else{
          prog_class <- "success"
        }
        share <- shares$share[i]
        shares_html <- paste0("Space used in share ", share, " (", utils:::format.object_size(as.numeric(shares$total[i]), "auto"), "):<div class=\"progress\"><div class=\"progress-bar progress-bar-", prog_class, "\" role=\"progressbar\" aria-valuenow=", per_used, " aria-valuemin=\"0\" aria-valuemax=\"100\" style=\"width: ", per_used, "%\">
    ", per_used, "%</div>
</div>")
      }
    }
    
    tagList(
      box(
        title = "Project Shares", width = NULL, solidHeader = TRUE, status = "primary",
        HTML(shares_html)
      )
    )
  })
  
  #folderlist----
  output$folderlist <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    page <- query['p']
    
    if (page == "NULL"){
      page = 0
    }
    
    page <- as.numeric(page)
    folders_per_page <- 15
    
    offset = page * folders_per_page
    
    folders_q <- paste0("SELECT project_folder, folder_id FROM folders WHERE project_id = ", project_id, " ORDER BY date DESC, project_folder DESC LIMIT ", folders_per_page, " OFFSET ", offset)
    flog.info(paste0("folders_q: ", folders_q), name = "dashboard")
    folders <- dbGetQuery(db, folders_q)
    
    no_folders_q <- paste0("SELECT count(*) as no_folders FROM folders WHERE project_id = ", project_id)
    flog.info(paste0("no_folders_q: ", no_folders_q), name = "dashboard")
    no_folders <- dbGetQuery(db, no_folders_q)[1]
    no_folders <- as.integer(no_folders[1,1])
    
    list_of_folders <- paste0("<div class=\"list-group\">")
    
    if (dim(folders)[1] > 0){
      for (i in 1:dim(folders)[1]){
        
        if (as.character(folders$folder_id[i]) == as.character(which_folder)){
          this_folder <- paste0("<a href=\"./?p=", page, "&folder=", folders$folder_id[i], "\" class=\"list-group-item active\">", folders$project_folder[i])
        }else{
          this_folder <- paste0("<a href=\"./?p=", page, "&folder=", folders$folder_id[i], "\" class=\"list-group-item\">", folders$project_folder[i])
        }
        
        #Count files
        count_files <- paste0("SELECT count(*) as no_files from files where folder_id = ", folders$folder_id[i])
        flog.info(paste0("count_files: ", count_files), name = "dashboard")
        folder_files <- dbGetQuery(db, count_files)
        this_folder <- paste0(this_folder, " <span class=\"badge\" title=\"No. of files\">", folder_files$no_files, "</span><p class=\"list-group-item-text\">")
        
        #Check subfolders
        folder_subdirs_q <- paste0("SELECT status from folders where folder_id = ", folders$folder_id[i])
        flog.info(paste0("folder_subdirs_q: ", folder_subdirs_q), name = "dashboard")
        folder_subdirs <- dbGetQuery(db, folder_subdirs_q)
        if (folder_subdirs == 9){
          this_folder <- paste0(this_folder, "<span class=\"label label-danger\" title=\"Missing subfolders\">Error</span> ")
        }
        
        #Only if there are any files
        if (folder_files$no_files > 0){
          
          file_checks_all <- paste(file_checks, collapse = ",")
          
          error_list <- paste0("SELECT COUNT(DISTINCT file_id) as no_files FROM file_checks WHERE check_results = 1 AND file_check = ANY('{", file_checks_all, "}'::text[]) AND file_id in (SELECT file_id from files where folder_id = ", folders$folder_id[i], ")")
          error_list <- dbGetQuery(db, error_list)
          error_list_count <- error_list$no_files

          if (error_list_count == 0){
            #Check if all have been checked
            check_list <- paste0("SELECT COUNT(DISTINCT file_id) as no_files FROM file_checks WHERE check_results = 9 AND file_check = ANY('{", file_checks_all, "}'::text[]) AND file_id in (SELECT file_id from files where folder_id = ", folders$folder_id[i], ")")
            
            check_list <- dbGetQuery(db, check_list)
            checked_list_count <- check_list$no_files  
            
            if (checked_list_count == 0){
              this_folder <- paste0(this_folder, " <span class=\"label label-success\" title=\"Files passed validation tests\">Files OK</span> ")
            }
            
          }else if (error_list_count > 0){
            this_folder <- paste0(this_folder, " <span class=\"label label-danger\" title=\"Files with errors\">Files with Errors</span> ")
          }
          
          #MD5 ----
          if (project_type == "tif"){
            md5_file_tif <- dbGetQuery(db, paste0("SELECT md5 FROM folders_md5 WHERE md5_type = 'tif' AND folder_id = ", folders$folder_id[i]))
            md5_file_raw <- dbGetQuery(db, paste0("SELECT md5 FROM folders_md5 WHERE md5_type = 'raw' AND folder_id = ", folders$folder_id[i]))
            
            if (dim(md5_file_tif)[1] == 0 || dim(md5_file_raw)[1] == 0){
              this_folder <- paste0(this_folder, " <span class=\"label label-default\">MD5 Files pending</span> ")
            }else if (md5_file_tif$md5 == 0 && md5_file_raw$md5 == 0){
              this_folder <- paste0(this_folder, " <span class=\"label label-success\">MD5 Files OK</span> ")
            }else{
              this_folder <- paste0(this_folder, " <span class=\"label label-warning\">MD5 Files missing</span> ")
            }
          }
          

        }else{
          this_folder <- paste0(this_folder, " <span class=\"label label-default\" title=\"No files in folder\">Empty</span> ")
        }
        
        unknown_file <- dbGetQuery(db, paste0("SELECT status FROM folders WHERE folder_id = ", folders$folder_id[i]))
        if (unknown_file$status == 1){
          this_folder <- paste0(this_folder, " <span class=\"label label-warning\" title=\"Unknown file found in folder\">Unknown File</span> ")
        }
        
        #QC
        if (!exists("project_qc")){
          project_qc = FALSE
        }
        if (project_qc == TRUE){
          folder_qc <- paste0("SELECT qc_pass from qc_lots l, qc_lots_folders f where l.qc_lot_id = f.qc_lot_id AND f.folder_id = ", folders$folder_id[i])
          flog.info(paste0("folder_qc: ", folder_qc), name = "dashboard")
          folder_qc_status <- dbGetQuery(db, folder_qc)
          if (dim(folder_qc_status)[1] == 0){
            this_folder <- paste0(this_folder, "<span class=\"label label-default\" title=\"QC Pending\">QC Pending</span> ")
          }else if (dim(folder_qc_status)[1] == 1){
            if (folder_qc_status == TRUE){
              this_folder <- paste0(this_folder, "<span class=\"label label-success\" title=\"Folder passed QC\">QC OK</span> ")
            }else if (folder_qc_status == FALSE){
              this_folder <- paste0(this_folder, "<span class=\"label label-danger\" title=\"Folder failed QC\">QC Failed</span> ")
            }
          }
        }
        
        #Check if delivered to DAMS
        delivered_dams_q <- paste0("SELECT delivered_to_dams from folders where folder_id = ", folders$folder_id[i])
        flog.info(paste0("delivered_dams_q: ", delivered_dams_q), name = "dashboard")
        delivered_dams <- dbGetQuery(db, delivered_dams_q)

        if (delivered_dams[1] == 1){
          this_folder <- paste0(this_folder, "</p><p><span class=\"label label-success\" title=\"Folder in DAMS\">In DAMS</span>")
          }else if (delivered_dams[1] == 0){
            this_folder <- paste0(this_folder, "</p><p><span class=\"label label-warning\" title=\"Ready for DAMS\">Ready for DAMS</span>")
          }
        
        this_folder <- paste0(this_folder, "</p></a>")
        list_of_folders <- paste0(list_of_folders, this_folder)
      }
    }
    
    
    if (no_folders > folders_per_page){
      if (page > 0){
        if (no_folders > ((page + 1) * folders_per_page)){
          list_of_folders <- paste0(list_of_folders, "<br><a href=\"./?p=", page - 1, "\" type=\"button\" class=\"btn btn-primary btn-xs pull-left\"><span class=\"glyphicon glyphicon-backward\" aria-hidden=\"true\"></span> Prev page</a><a href=\"./?p=", page + 1, "\" type=\"button\" class=\"btn btn-primary btn-xs pull-right\"><span class=\"glyphicon glyphicon-forward\" aria-hidden=\"true\"></span> Next page</a>")
        }else{
          list_of_folders <- paste0(list_of_folders, "<br><a href=\"./?p=", page - 1, "\" type=\"button\" class=\"btn btn-primary btn-xs pull-left\"><span class=\"glyphicon glyphicon-backward\" aria-hidden=\"true\"></span> Prev page</a>")
        }
      }else{
        list_of_folders <- paste0(list_of_folders, "<br><a href=\"./?p=", page + 1, "\" type=\"button\" class=\"btn btn-primary btn-xs pull-right\"><span class=\"glyphicon glyphicon-forward\" aria-hidden=\"true\"></span> Next page</a>")
      }
      
    }
    
    list_of_folders <- paste0(list_of_folders, "</div>")
    HTML(list_of_folders)
  })
  

  #project_alert----
  output$project_alert <- renderUI({
  
    proj_alert_q <- paste0("SELECT project_message, to_char(updated_at, 'Mon DD, YYYY HH24:MI:SS') as date FROM projects_alerts WHERE active = 't' AND project_id = ", project_id)
    flog.info(paste0("proj_alert_q: ", proj_alert_q), name = "dashboard")
    proj_alert <- dbGetQuery(db, proj_alert_q)
    if (dim(proj_alert)[1] > 0){
      to_print <- "<div class=\"alert alert-warning\" role=\"alert\"><strong>Notice:</strong> "
      for (a in seq(1, dim(proj_alert)[1])){
        to_print <- paste0(to_print, proj_alert$project_message[a], "<br>")
      }
      to_print <- paste0(to_print, "</div>")
      HTML(to_print)
    }else{
      req(FALSE)
    }
    
  })
  
  
  
  #folderinfo1----
  output$folderinfo1 <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    if (which_folder == "NULL"){
      p("Select a folder from the list on the left")
    }else{
      folder_info_q <- paste0("SELECT *, to_char(updated_at, 'Mon DD, YYYY HH24:MI:SS') as import_date, to_char(updated_at, 'Mon DD, YYYY HH24:MI:SS') as updated_at_formatted FROM folders WHERE folder_id = ", which_folder)
      flog.info(paste0("folder_info_q: ", folder_info_q), name = "dashboard")
      folder_info <- dbGetQuery(db, folder_info_q)
      if (dim(folder_info)[1] == 0){
        p("Select a folder from the list on the left")
      }else{
        HTML(paste0("<h3><span class=\"label label-primary\">", folder_info$project_folder, "</span></h3>"))
      }
    }
  })
  
  

  #Folder progress----
  observeEvent(input$dayprogress, {
    
    showModal(modalDialog(
      size = "l",
      title = "Progress by Day",
      uiOutput("proj_dates"),
      plotOutput("dayplot"),
      br(),
      downloadButton("downloadData1", "Download as CSV", class = "btn-primary"),
      easyClose = TRUE
    ))
  })
  
  
  
  output$proj_dates <- renderUI({
    dates_q <- paste0("SELECT DISTINCT date_trunc('day', created_at) AS date FROM files WHERE folder_id in (SELECT folder_id from folders where project_id = ", project_id, ") ORDER BY date DESC")
    flog.info(paste0("dates_q: ", dates_q), name = "dashboard")
    proj_dates <- dbGetQuery(db, dates_q)
    
    proj_dates <- na.omit(proj_dates)
    print(proj_dates)
    selectInput('this_date', "Select a date", choices = proj_dates$date)
  
  })
  
  output$dayplot <- renderPlot({
    req(input$this_date)
    folder_progress_q <- paste0("with t as (
                          select generate_series('", input$this_date, " 06:00:00'::timestamp, '", input$this_date, " 19:00:00'::timestamp, '5 minutes') as int)
                        select int as time,
                            count(*)::int as no_files
                        from t
                           left join files tmp on 
                                 (tmp.created_at >= t.int and 
                                  tmp.created_at < (t.int + interval '5 minutes'))
                        where date_trunc('day', tmp.created_at) = '", input$this_date, "'
                        group by int
                        order by int")
    flog.info(paste0("folder_progress_q: ", folder_progress_q), name = "dashboard")
    folder_progress <<- dbGetQuery(db, folder_progress_q)
    
    ggplot(folder_progress, mapping = aes(x = as.POSIXct(time), y = no_files)) + geom_col() + labs(x = "Time", y = "No. of files") + scale_x_datetime(name = "Time", date_breaks = "15 min", date_labels = "%H:%M") + theme(axis.text.x = element_text(angle = 90))
  })
  
  
  #downloadData1----
  output$downloadData1 <- downloadHandler(
    filename = function() {
      paste(input$this_date, ".csv", sep = "")
    },
    content = function(file) {
      write.csv(folder_progress, file, row.names = FALSE)
    }
  )
  
  
  #folderinfo2----
  output$folderinfo2 <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    if (which_folder != "NULL"){
      folder_info_q <- paste0("SELECT *, to_char(updated_at, 'Mon DD, YYYY HH24:MI:SS') as import_date, to_char(updated_at, 'Mon DD, YYYY HH24:MI:SS') as updated_at_formatted FROM folders WHERE folder_id = ", which_folder)
      flog.info(paste0("folder_info_q: ", folder_info_q), name = "dashboard")
      folder_info <- dbGetQuery(db, folder_info_q)
      if (dim(folder_info)[1] > 0){
        this_folder <- ""
        
        folder_subdirs <- dbGetQuery(db, paste0("SELECT status, error_info from folders where folder_id = '", which_folder, "'"))
        error_msg <- ""
        if (folder_subdirs$status == 9){
          this_folder <- paste0(this_folder, "<h4><span class=\"label label-danger\" title=\"Missing subfolders\">", folder_subdirs$error_info, "</span></h4>")
        }
        
        
        #Folder MD5----
        #MD5 ----
        if (project_type == "tif"){
          md5_file_tif <- dbGetQuery(db, paste0("SELECT md5 FROM folders_md5 WHERE md5_type = 'tif' AND folder_id = ", which_folder))
          md5_file_raw <- dbGetQuery(db, paste0("SELECT md5 FROM folders_md5 WHERE md5_type = 'raw' AND folder_id = ", which_folder))
          
          if (dim(md5_file_tif)[1] == 0){
            this_folder <- paste0(this_folder, " <span class=\"label label-default\">TIF MD5 File pending</span> ")
          }else if (md5_file_tif$md5 == 0){
            this_folder <- paste0(this_folder, " <span class=\"label label-success\">TIF MD5 File OK</span> ")
          }else{
            this_folder <- paste0(this_folder, " <span class=\"label label-warning\">TIF MD5 File missing</span> ")
          }
          
          if (dim(md5_file_raw)[1] == 0){
            this_folder <- paste0(this_folder, " <span class=\"label label-default\">RAW MD5 File pending</span> ")
          }else if (md5_file_raw$md5 == 0){
            this_folder <- paste0(this_folder, " <span class=\"label label-success\">RAW MD5 File OK</span> ")
          }else{
            this_folder <- paste0(this_folder, " <span class=\"label label-warning\">RAW MD5 File missing</span> ")
          }
        }
        
        if (!exists("project_qc")){
          project_qc = FALSE
        }
        if (project_qc == TRUE){
          folder_qc <- paste0("SELECT qc_pass from qc_lots l, qc_lots_folders f where l.qc_lot_id = f.qc_lot_id AND f.folder_id = ", which_folder)
          flog.info(paste0("folder_qc: ", folder_qc), name = "dashboard")
          folder_qc_status <- dbGetQuery(db, folder_qc)
          if (dim(folder_qc_status)[1] == 0){
            this_folder <- paste0(this_folder, "<span class=\"label label-default\" title=\"QC Pending\">QC Pending</span> ")
          }else if (dim(folder_qc_status)[1] == 1){
            if (folder_qc_status == TRUE){
              this_folder <- paste0(this_folder, "<span class=\"label label-success\" title=\"Folder passed QC\">QC OK</span> ")
            }else if (folder_qc_status == FALSE){
              this_folder <- paste0(this_folder, "<span class=\"label label-danger\" title=\"Folder failed QC\">QC Failed</span> ")
            }
          }
        }
        
        #Check if delivered to DAMS
        delivered_dams_q <- paste0("SELECT delivered_to_dams from folders where folder_id = ", which_folder)
        flog.info(paste0("delivered_dams_q: ", delivered_dams_q), name = "dashboard")
        delivered_dams <- dbGetQuery(db, delivered_dams_q)
        
        if (delivered_dams[1] == 1){
          this_folder <- paste0(this_folder, "<span class=\"label label-success\" title=\"Folder in DAMS\">In DAMS</span>")
        }else if (delivered_dams[1] == 0){
          this_folder <- paste0(this_folder, "<span class=\"label label-warning\" title=\"Ready for DAMS\">Ready for DAMS</span>")
        }
        
        HTML(this_folder)
        
      }
    }
  })
  
  
  
  #Files table ----
  output$tableheading <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    if (which_folder != "NULL"){
      HTML("<p><strong>Click on a file in the table below to see details:</strong></p>")
    }
  })
  
  output$files_table <- DT::renderDataTable({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    req(which_folder != "NULL")
    
    folder_info <- dbGetQuery(db, paste0("SELECT *, to_char(updated_at, 'Mon DD, YYYY HH24:MI:SS') as import_date FROM folders WHERE folder_id = ", which_folder))
    if (dim(folder_info)[1] == 0){
      req(FALSE)
    }
    
    files_query <- paste0("SELECT file_id, file_name FROM files WHERE folder_id = ", which_folder)
    files_list <- dbGetQuery(db, files_query)
    
    checks_query <- paste0("SELECT project_checks FROM projects WHERE project_id = ", project_id)
    checks_list <- strsplit(dbGetQuery(db, checks_query)[1,1], ",")[[1]]
    
    folder_check_query <- paste0("
                  SELECT f.file_name, fc.file_check, CASE WHEN fc.check_results = 0 THEN 'OK' WHEN fc.check_results = 9 THEN 'Pending' WHEN fc.check_results = 1 THEN 'Failed' END as check_results, fc.check_info 
                  FROM files f, file_checks fc where f.file_id = fc.file_id AND f.folder_id = ", which_folder)
                  
    files_list <- dbGetQuery(db, folder_check_query)

    fileslist_df <<- reshape::cast(files_list, file_name ~ file_check, value = "check_results")

    no_cols <- dim(fileslist_df)[2]
    
    DT::datatable(
      fileslist_df, 
          class = 'compact',
          escape = FALSE, 
          options = list(
                searching = TRUE, 
                ordering = TRUE, 
                pageLength = 50, 
                paging = TRUE, 
                language = list(zeroRecords = "Folder has no files yet"),
                scrollX = TRUE
              ),
          rownames = FALSE, 
          selection = 'single') %>% DT::formatStyle(
            2:no_cols,
            backgroundColor = DT::styleEqual(c("OK", "Failed", "Pending"), c('#00a65a', '#d9534f', '#777')),
            color = 'white'
          )
  })
  
  
  #pp_table----
  output$pp_table <- DT::renderDataTable({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    req(which_folder != "NULL")
    
    files_query <- paste0("SELECT file_id, file_name FROM files WHERE folder_id = ", which_folder)
    files_list <- dbGetQuery(db, files_query)
    
    checks_query <- paste0("SELECT project_postprocessing FROM projects WHERE project_id = ", project_id)
    checks_list <- strsplit(dbGetQuery(db, checks_query)[1,1], ",")[[1]]
    
    folder_check_query <- paste0("SELECT f.file_name, fp.post_step, CASE WHEN fp.post_results = 0 THEN 'Completed' WHEN fp.post_results = 9 THEN 'Pending' WHEN fp.post_results = 1 THEN 'Failed' END as post_results, fp.post_info
                  FROM files f, file_postprocessing fp where f.file_id = fp.file_id AND f.folder_id = ", which_folder)
    
    files_list <- dbGetQuery(db, folder_check_query)
    
    if (dim(files_list)[1] > 0){
      fileslist_df2 <- reshape::cast(files_list, file_name ~ post_step, value = "post_results")
      
      list_names <- names(fileslist_df2)
      
      list_names <- list_names[list_names != "file_name"]
      list_names <- list_names[list_names != "ready_for_dams"]
      list_names <- list_names[list_names != "in_dams"]
      list_names <- list_names[list_names != "md5_matches"]
      
      fileslist_df2 <- fileslist_df2[c("file_name", "md5_matches", list_names, "ready_for_dams", "in_dams")]
    }else{
      fileslist_df2 <- files_list
    }
    
    no_cols <- dim(fileslist_df2)[2]
    
    DT::datatable(
      fileslist_df2, 
      class = 'compact',
      escape = FALSE, 
      options = list(
        searching = TRUE, 
        ordering = TRUE, 
        pageLength = 50, 
        paging = TRUE, 
        language = list(zeroRecords = "Not ready yet"),
        scrollX = TRUE
      ),
      rownames = FALSE, 
      selection = 'single') %>% DT::formatStyle(
        2:no_cols,
        backgroundColor = DT::styleEqual(c("Completed", "Failed", "Pending"), c('#00a65a', '#d9534f', '#777')),
        color = 'white'
      )
  })
  
  
  #fileinfo ----
  output$fileinfo <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    req(which_folder != "NULL")
    
    req(input$files_table_rows_selected)
    
    file_name <- fileslist_df[input$files_table_rows_selected, ]$file_name
    
    file_info_q <- paste0("SELECT *, to_char(updated_at, 'Mon DD, YYYY HH24:MI:SS') as date, to_char(file_timestamp, 'Mon DD, YYYY HH24:MI:SS') as filedate FROM files WHERE file_name = '", file_name, "' AND folder_id = ", which_folder)
    flog.info(paste0("file_info_q: ", file_info_q), name = "dashboard")
    file_info <- dbGetQuery(db, file_info_q)

    file_id <- file_info$file_id
    
    html_to_print <- "<h4>File info</h4><dl>"
    
    #Image preview ----
    observeEvent(input$showpreview, {
      showModal(modalDialog(
        size = "l",
        title = "Preview Image",
        HTML(paste0("<img src=\"http://dpogis.si.edu/mdpp/previewimage?file_id=", file_id, "\" width = \"100%\">")),
        easyClose = TRUE
      ))
    })
    
    
    if (project_type == "tif"){
        html_to_print <- paste0(html_to_print, HTML("<dt>TIF preview:</dt><dd>"))
        html_to_print <- paste0(html_to_print, actionLink("showpreview", label = HTML(paste0("<img src = \"http://dpogis.si.edu/mdpp/previewimage?file_id=", file_id, "\" width = \"160px\" height = \"auto\"></dd>"))))
    }
    
    html_to_print <- paste0(html_to_print, "<dt>File name</dt><dd>", file_info$file_name, "</dd>")
    html_to_print <- paste0(html_to_print, "<dt>File ID</dt><dd>", file_info$file_id, "</dd>")
    html_to_print <- paste0(html_to_print, "<dt>Item number</dt><dd>", file_info$item_no, "</dd>")
    html_to_print <- paste0(html_to_print, "<dt>File timestamp</dt><dd>", file_info$filedate, "</dd>")
    html_to_print <- paste0(html_to_print, "<dt>Imported on</dt><dd>", file_info$date, "</dd>")
    
    #file_exists
    if (stringr::str_detect(file_checks_list, "file_exists")){
      html_to_print <- paste0(html_to_print, "<dt>File exists</dt>")
      if (file_info$file_exists == 0){
        html_to_print <- paste0(html_to_print, "<dd>", file_info$file_exists)
      }else if (file_info$file_exists == 1){
        html_to_print <- paste0(html_to_print, "<dd class=\"bg-danger\">", file_info$file_exists)
      }else{
        html_to_print <- paste0(html_to_print, "<dd class=\"bg-warning\">", file_info$file_exists)
      }
      html_to_print <- paste0(html_to_print, "</dd>")
    }
    
    #TIF md5----
    if (project_type == "tif"){
      info_q <- paste0("SELECT md5 FROM file_md5 WHERE filetype = 'tif' AND file_id = ", file_id)
      flog.info(paste0("info_q: ", info_q), name = "dashboard")
      md5 <- dbGetQuery(db, info_q)
      
      if (dim(md5)[1] == 0){
        html_to_print <- paste0(html_to_print, "<dt>TIF MD5</dt><dd>NA</dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>TIF MD5</dt><dd>", md5, "</dd>")
      }
      
      #raw
      info_q <- paste0("SELECT md5 FROM file_md5 WHERE filetype = 'raw' AND file_id = ", file_id)
      flog.info(paste0("info_q: ", info_q), name = "dashboard")
      md5 <- dbGetQuery(db, info_q)
      
      if (dim(md5)[1] == 0){
        html_to_print <- paste0(html_to_print, "<dt>RAW MD5</dt><dd>NA</dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>RAW MD5</dt><dd>", md5, "</dd>")
      }
    }
    
    #WAV MD5
    if (project_type == "sound"){
      info_q <- paste0("SELECT md5 FROM file_md5 WHERE filetype = 'wav' AND file_id = ", file_id)
      flog.info(paste0("info_q: ", info_q), name = "dashboard")
      md5 <- dbGetQuery(db, info_q)
      
      if (dim(md5)[1] == 0){
        html_to_print <- paste0(html_to_print, "<dt>WAV MD5</dt><dd>NA</dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>WAV MD5</dt><dd>", md5, "</dd>")
      }
    }
    
    #valid_name
    if (stringr::str_detect(file_checks_list, "valid_name")){
      info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'valid_name' AND file_id = ", file_id)
      flog.info(paste0("info_q: ", info_q), name = "dashboard")
      check_res <- dbGetQuery(db, info_q)
      
      if (dim(check_res)[1] == 1){
        if (check_res$check_results == 0){
          html_to_print <- paste0(html_to_print, "<dt>Valid filename</dt><dd>", check_res$check_info, "</dd>")  
        }else if (check_res$check_results == 1){
          html_to_print <- paste0(html_to_print, "<dt>Valid filename</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
        }else if (check_res$check_results == 9){
          html_to_print <- paste0(html_to_print, "<dt>Valid filename</dt><dd class=\"bg-warning\">Not checked yet</dd>")
        }
      }
    }
    
    #raw_pair
    if (stringr::str_detect(file_checks_list, "raw_pair")){
      info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'raw_pair' AND file_id = ", file_id)
      flog.info(paste0("info_q: ", info_q), name = "dashboard")
      check_res <- dbGetQuery(db, info_q)
      
      if (dim(check_res)[1] == 1){
        if (check_res$check_results == 0){
          html_to_print <- paste0(html_to_print, "<dt>Raw file</dt><dd>", check_res$check_info, "</dd>")  
        }else if (check_res$check_results == 1){
          html_to_print <- paste0(html_to_print, "<dt>Raw file</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
        }else if (check_res$check_results == 9){
          html_to_print <- paste0(html_to_print, "<dt>Raw file</dt><dd class=\"bg-warning\">Not checked yet</dd>")
        }
      }
    }
  
    #unique_file ----
    if (stringr::str_detect(file_checks_list, "unique_file")){
      info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'unique_file' AND file_id = ", file_id)
      flog.info(paste0("info_q: ", info_q), name = "dashboard")
      check_res <- dbGetQuery(db, info_q)
      
      if (dim(check_res)[1] == 1){
        if (check_res$check_results == 0){
          html_to_print <- paste0(html_to_print, "<dt>Unique file</dt><dd>OK</dd>")  
        }else if (check_res$check_results == 1){
          html_to_print <- paste0(html_to_print, "<dt>Unique file</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
        }else if (check_res$check_results == 9){
          html_to_print <- paste0(html_to_print, "<dt>Unique file</dt><dd class=\"bg-warning\">Not checked yet</dd>")
        }
      }
    }
      
    #old_names ----
    if (stringr::str_detect(file_checks_list, "old_name")){
      info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'old_name' AND file_id = ", file_id)
      flog.info(paste0("info_q: ", info_q), name = "dashboard")
      check_res <- dbGetQuery(db, info_q)
      
      if (dim(check_res)[1] == 1){
        if (check_res$check_results == 0){
          html_to_print <- paste0(html_to_print, "<dt>Unique file</dt><dd>OK</dd>")  
        }else if (check_res$check_results == 1){
          html_to_print <- paste0(html_to_print, "<dt>Unique file</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
        }else if (check_res$check_results == 9){
          html_to_print <- paste0(html_to_print, "<dt>Unique file</dt><dd class=\"bg-warning\">Not checked yet</dd>")
        }
      }
    }
    
    #JHOVE ----
    if (stringr::str_detect(file_checks_list, "jhove")){
      info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'jhove' AND file_id = ", file_id)
      flog.info(paste0("info_q: ", info_q), name = "dashboard")
      check_res <- dbGetQuery(db, info_q)
      
      if (dim(check_res)[1] == 1){
        if (check_res$check_results == 0){
          html_to_print <- paste0(html_to_print, "<dt>JHOVE</dt><dd>", check_res$check_info, "</dd>")
        }else if (check_res$check_results == 1){
          html_to_print <- paste0(html_to_print, "<dt>JHOVE</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
        }else if (check_res$check_results == 9){
          html_to_print <- paste0(html_to_print, "<dt>JHOVE</dt><dd class=\"bg-warning\">Not checked yet</dd>")
        }
      }
    }
    
    #tifpages ----
    if (project_type == "tif"){
      if (stringr::str_detect(file_checks_list, "tifpages")){
        info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'tifpages' AND file_id = ", file_id)
        flog.info(paste0("info_q: ", info_q), name = "dashboard")
        check_res <- dbGetQuery(db, info_q)
        
        if (dim(check_res)[1] == 1){
          if (check_res$check_results == 0){
            html_to_print <- paste0(html_to_print, "<dt>Multiple pages in TIF</dt><dd>", check_res$check_info, "</dd>")
          }else if (check_res$check_results == 1){
            html_to_print <- paste0(html_to_print, "<dt>Multiple pages in TIF</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
          }else if (check_res$check_results == 9){
            html_to_print <- paste0(html_to_print, "<dt>Multiple pages in TIF</dt><dd class=\"bg-warning\">Not checked yet</dd>")
          }
        }
      }
    }
    
    #tifpages ----
    if (project_type == "tif"){
      if (stringr::str_detect(file_checks_list, "tif_compression")){
        info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'tif_compression' AND file_id = ", file_id)
        flog.info(paste0("info_q: ", info_q), name = "dashboard")
        check_res <- dbGetQuery(db, info_q)
        
        if (dim(check_res)[1] == 1){
          if (check_res$check_results == 0){
            html_to_print <- paste0(html_to_print, "<dt>TIF Compression</dt><dd>", check_res$check_info, "</dd>")
          }else if (check_res$check_results == 1){
            html_to_print <- paste0(html_to_print, "<dt>TIF Compression</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
          }else if (check_res$check_results == 9){
            html_to_print <- paste0(html_to_print, "<dt>TIF Compression</dt><dd class=\"bg-warning\">Not checked yet</dd>")
          }
        }
      }
    }
    
    #ImageMagick ----
    if (project_type == "tif"){
      if (stringr::str_detect(file_checks_list, "magick")){
        info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'magick' AND file_id = ", file_id)
        flog.info(paste0("info_q: ", info_q), name = "dashboard")
        check_res <- dbGetQuery(db, info_q)
        
        m_info <- check_res$check_info
        
        observeEvent(input$showmagic, {
          showModal(modalDialog(
            size = "l",
            title = "Imagemagick Info",
            p("magick"),
            pre(m_info),
            easyClose = TRUE
          ))
        })
        
        if (dim(check_res)[1] == 1){
          if (check_res$check_results == 0){
            
            html_to_print <- paste0(html_to_print, "<dt>Imagemagick</dt><dd>OK ", actionLink("showmagic", label = "[More info]"), "</dd>")
            
          }else if (check_res$check_results == 1){
            html_to_print <- paste0(html_to_print, "<dt>Imagemagick</dt><dd class=\"bg-danger\"><pre>", check_res$check_info, "</pre></dd>")  
          }else if (check_res$check_results == 9){
            html_to_print <- paste0(html_to_print, "<dt>Imagemagick</dt><dd class=\"bg-warning\">Not checked yet</dd>")
          }
        }
      }
      
      #stitched_jpg ----
      if (stringr::str_detect(file_checks_list, "stitched_jpg")){
        info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'stitched_jpg' AND file_id = ", file_id)
        flog.info(paste0("info_q: ", info_q), name = "dashboard")
        check_res <- dbGetQuery(db, info_q)
        
        j_info <- check_res$check_info
        
        observeEvent(input$showjpg, {
          showModal(modalDialog(
            size = "l",
            title = "Imagemagick Info of Stitched JPG",
            p("stitched"),
            pre(j_info),
            easyClose = TRUE
          ))
        })
        
        if (dim(check_res)[1] == 1){
          if (check_res$check_results == 0){
            
            html_to_print <- paste0(html_to_print, "<dt>Stitched JPG</dt><dd>OK ", actionLink("showjpg", label = "[More info]"), "</dd>")
            
          }else if (check_res$check_results == 1){
            html_to_print <- paste0(html_to_print, "<dt>Stitched JPG</dt><dd class=\"bg-danger\"><pre>", check_res$check_info, "</pre></dd>")  
          }else if (check_res$check_results == 9){
            html_to_print <- paste0(html_to_print, "<dt>Stitched JPG</dt><dd class=\"bg-warning\">Not checked yet</dd>")
          }
        }
      }
    }
    
    
    
    
    #Metadata----
    html_to_print <- paste0(html_to_print, "<dt>Metadata</dt><dd>", actionLink("exiftif", label = "TIF File Metadata"))
    html_to_print <- paste0(html_to_print, "<br>", actionLink("exifraw", label = "RAW File Metadata"), "</dd>")
    
    tifexif_q <- paste0("SELECT taggroup, tag, value FROM files_exif WHERE filetype = 'TIF' AND file_id = ", file_id, " ORDER BY taggroup, tag")
    flog.info(paste0("tifexif_q: ", tifexif_q), name = "dashboard")
    tifexif <- dbGetQuery(db, tifexif_q)
    
    output$tifexif_dt <- DT::renderDataTable({
    
      tifexif <- tifexif %>% dplyr::rename("Tag Group" = taggroup) %>% 
        dplyr::rename("Tag" = tag) %>% 
        dplyr::rename("Value" = value)
      
      DT::datatable(
        tifexif, 
        class = 'compact',
        escape = FALSE, 
        options = list(
          searching = TRUE, 
          ordering = TRUE, 
          pageLength = 50, 
          paging = TRUE, 
          scrollX = TRUE
        ),
        rownames = FALSE)
    })
    
    
    #exiftif----
    observeEvent(input$exiftif, {
      
      showModal(modalDialog(
        size = "l",
        title = "TIF EXIF Metadata",
        #HTML(display_tifexif),
        DT::dataTableOutput("tifexif_dt"),
        easyClose = TRUE
      ))
    })
    
    
    rawexif_q <- paste0("SELECT taggroup, tag, value FROM files_exif WHERE filetype = 'RAW' AND file_id = ", file_id, " ORDER BY taggroup, tag")
    flog.info(paste0("rawexif_q: ", rawexif_q), name = "dashboard")
    rawexif <- dbGetQuery(db, rawexif_q)
    
    output$rawexif_dt <- DT::renderDataTable({
      
      rawexif <- rawexif %>% dplyr::rename("Tag Group" = taggroup) %>% 
        dplyr::rename("Tag" = tag) %>% 
        dplyr::rename("Value" = value)
      
      DT::datatable(
        rawexif, 
        class = 'compact',
        escape = FALSE, 
        options = list(
          searching = TRUE, 
          ordering = TRUE, 
          pageLength = 50, 
          paging = TRUE, 
          scrollX = TRUE
        ),
        rownames = FALSE)
    })
    
    #exifraw----
    observeEvent(input$exifraw, {
      
      showModal(modalDialog(
        size = "l",
        title = "RAW EXIF Metadata",
        #HTML(display_rawexif),
        DT::dataTableOutput("rawexif_dt"),
        easyClose = TRUE
      ))
    })
    
    
    #WAVS ----
    if (project_type == "wav"){
      #filetype ----
      if (stringr::str_detect(file_checks_list, "filetype")){
        info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'filetype' AND file_id = ", file_id)
        flog.info(paste0("info_q: ", info_q), name = "dashboard")
        check_res <- dbGetQuery(db, info_q)
        
        if (dim(check_res)[1] == 1){
          if (check_res$check_results == 0){
            html_to_print <- paste0(html_to_print, "<dt>Filetype</dt><dd>", check_res$check_info, "</dd>")
          }else if (check_res$check_results == 1){
            html_to_print <- paste0(html_to_print, "<dt>Filetype</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
          }else if (check_res$check_results == 9){
            html_to_print <- paste0(html_to_print, "<dt>Filetype</dt><dd class=\"bg-warning\">Not checked yet</dd>")
          }
        }
      }
    
      if (stringr::str_detect(file_checks_list, "samprate")){
        info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'samprate' AND file_id = ", file_id)
        flog.info(paste0("info_q: ", info_q), name = "dashboard")
        check_res <- dbGetQuery(db, info_q)
        
        if (dim(check_res)[1] == 1){
          if (check_res$check_results == 0){
            html_to_print <- paste0(html_to_print, "<dt>Sampling rate</dt><dd>", check_res$check_info, "</dd>")
          }else if (check_res$check_results == 1){
            html_to_print <- paste0(html_to_print, "<dt>Sampling rate</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
          }else if (check_res$check_results == 9){
            html_to_print <- paste0(html_to_print, "<dt>Sampling rate</dt><dd class=\"bg-warning\">Not checked yet</dd>")
          }
        }
      }
    
      if (stringr::str_detect(file_checks_list, "channels")){
        info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'channels' AND file_id = ", file_id)
        flog.info(paste0("info_q: ", info_q), name = "dashboard")
        check_res <- dbGetQuery(db, info_q)
        
        if (dim(check_res)[1] == 1){
          if (check_res$check_results == 0){
            html_to_print <- paste0(html_to_print, "<dt>No. of channels</dt><dd>", check_res$check_info, "</dd>")
          }else if (check_res$check_results == 1){
            html_to_print <- paste0(html_to_print, "<dt>No. of channels</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
          }else if (check_res$check_results == 9){
            html_to_print <- paste0(html_to_print, "<dt>No. of channels</dt><dd class=\"bg-warning\">Not checked yet</dd>")
          }
        }
      }
      
      if (stringr::str_detect(file_checks_list, "bits")){
        info_q <- paste0("SELECT * FROM file_checks WHERE file_check = 'bits' AND file_id = ", file_id)
        flog.info(paste0("info_q: ", info_q), name = "dashboard")
        check_res <- dbGetQuery(db, info_q)
        
        if (dim(check_res)[1] == 1){
          if (check_res$check_results == 0){
            html_to_print <- paste0(html_to_print, "<dt>Bits</dt><dd>", check_res$check_info, "</dd>")
          }else if (check_res$check_results == 1){
            html_to_print <- paste0(html_to_print, "<dt>Bits</dt><dd class=\"bg-danger\">", check_res$check_info, "</dd>")  
          }else if (check_res$check_results == 9){
            html_to_print <- paste0(html_to_print, "<dt>Bits</dt><dd class=\"bg-warning\">Not checked yet</dd>")
          }
        }
      }
    }
    
    html_to_print <- paste0(html_to_print, "</dl>")
    
    HTML(html_to_print)
  })
  
  
  #footer----
  output$footer <- renderUI({
      HTML(paste0("<h4 style=\"position: fixed; bottom: -10px; width: 100%; text-align: right; right: 0px; padding: 10px; background: white;\">", app_name, " ver. ", app_ver, " | <a href=\"", github_link, "\" target = _blank>Source code</a> | <a href=\"http://dpo.si.edu\" target = _blank><img src=\"dpologo.jpg\" width = \"238\" height=\"50\"></a></h4>"))
    })
  }



# Run app ----
shinyApp(ui = ui, server = server, onStart = function() {
  cat("Loading\n")
  #Load project ----
  onStop(function() {
    cat("Closing\n")
    #Close databases ----
    try(dbDisconnect(db), silent = TRUE)
    cat("Removing objects\n")
  })
})
