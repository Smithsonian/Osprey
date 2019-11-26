# Packages ----
library(shiny)
library(dplyr)
library(DBI)
library(DT)
library(futile.logger)
library(stringr)
library(shinycssloaders)
library(shinyjs)


# Settings ----
source("settings.R")
app_name <- "Image Quality Inspection"
app_ver <- "0.1.0"
github_link <- "https://github.com/Smithsonian/MDFileCheck"

options(stringsAsFactors = FALSE)
options(encoding = 'UTF-8')
source("functions.R")


#Logfile----
dir.create("logs", showWarnings = FALSE)
logfile <- paste0("logs/", format(Sys.time(), "%Y%m%d_%H%M%S"), ".txt")
flog.logger("qc", INFO, appender=appender.file(logfile))


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


project <- dbGetQuery(db, paste0("SELECT project_acronym FROM projects WHERE project_id = ", project_id))
proj_name <- paste0(project$project_acronym, " - QC page")

jsCode <- '
            shinyjs.getcookie = function(params) {
              var cookie = Cookies.get("qcid");
              if (typeof cookie !== "undefined") {
                Shiny.onInputChange("jscookie", cookie);
              } else {
                var cookie = "";
                Shiny.onInputChange("jscookie", cookie);
              }
            }
            shinyjs.setcookie = function(params) {
              Cookies.set("qcid", escape(params), { expires: 1 });  
              Shiny.onInputChange("jscookie", params);
            }
            shinyjs.rmcookie = function(params) {
              Cookies.remove("qcid");
              Shiny.onInputChange("jscookie", "");
            }
          '


# UI ----
ui <- fluidPage(
  
  tags$head(
    tags$script(src = "js.cookie.min.js")
  ),
  useShinyjs(),
  extendShinyjs(text = jsCode),
  
  tags$script(src = "jquery.elevateZoom-3.0.8.min.js"),
    
  #header
  #titlePanel(proj_name),
  title = proj_name,
  #Body
  fluidRow(
    column(width = 4,
           h2(proj_name)
    ),
    column(width = 7,
           p("")
    ),
    column(width = 1,
           uiOutput("userinfo")
    )
  ),
  fluidRow(
    column(width = 2,
           uiOutput("userlogin"),
           uiOutput("lotlisth"),
           uiOutput("lotlist1")
    ),
    column(width = 10,
           uiOutput("tableheading"),
           shinycssloaders::withSpinner(DT::dataTableOutput("lotqctable")),
           uiOutput("runqc"),
           br(),br(),br(),br(),br()
    )
  ),
  #Footer
  uiOutput("footer")
)


# Server ----
server <- function(input, output, session) {
  
  status <- reactiveVal(value = NULL)
  # check if a cookie is present and matching our super random sessionid
  observe({
    js$getcookie()
    
    if (!is.null(input$jscookie)) {
      status(paste0('in with sessionid ', input$jscookie))
    }
    else {
      status('out')
    }
  })
  
  status <- reactiveVal(value = NULL)
  # check if a cookie is present and matching our super random sessionid  
  observe({
    js$getcookie()
    if (!is.null(input$jscookie)) {
      user_id <- dbGetQuery(db, paste0("SELECT c.user_id FROM qc_users_cookies c, qc_users u WHERE c.user_id = u.user_id AND u.project_id = ", project_id, " AND c.cookie = '", input$jscookie, "'"))
      
      if (dim(user_id)[1] == 0){
        status('out')
        js$rmcookie()
      }
    }
  })
  
  
  
  #userlogin----
  output$userlogin <- renderUI({
    js$getcookie()
    if (is.null(input$jscookie) || input$jscookie == ""){
      tagList(
        br(),br(),br(),br(),
        textInput("username", "Username:"),
        passwordInput("password", "Password:"),
        actionButton("login", "Login")
      )
    }else{
      user_id <- dbGetQuery(db, paste0("SELECT c.user_id, u.username FROM qc_users_cookies c, qc_users u WHERE c.user_id = u.user_id AND u.project_id = ", project_id, " AND c.cookie = '", input$jscookie, "'"))

      if (dim(user_id)[1] == 0){
        js$rmcookie()
        tagList(
          br(),br(),br(),br(),
          textInput("username", "Username:", value = 'villanueval'),
          passwordInput("password", "Password:", value = 'qccontrol'),
          actionButton("login", "Login")
        )
      }else{
        session$userData$user_id <- user_id$user_id
        session$userData$username <- user_id$username
        HTML("&nbsp;")
      }
    }
  })
  
  
  
  #observeEvent_login----
  observeEvent(input$login, {
    is_user <- dbGetQuery(db, paste0("SELECT user_id FROM qc_users WHERE project_id = ", project_id, " AND username = '", input$username, "' AND pass = MD5('", input$password, "')"))
    if (dim(is_user)[1] == 0){
      output$userlogin <- renderUI({
        p("Error: User not found or password not correct.")
      }) 
    }else{
      user_id <- dbGetQuery(db, paste0("SELECT c.user_id FROM qc_users_cookies c, qc_users u WHERE c.user_id = u.user_id AND u.project_id = ", project_id, " AND c.cookie = '", input$jscookie, "'"))

      if (dim(user_id)[1] == 0){
        sessionid <- paste(
          collapse = '',
          sample(x = c(letters, LETTERS, 0:9), size = 64, replace = TRUE)
        )
        
        n <- dbSendQuery(db, paste0("INSERT INTO qc_users_cookies (user_id, cookie) VALUES (", is_user$user_id, ", '", sessionid, "')"))
        dbClearResult(n)
        js$setcookie(sessionid)
        session$userData$user_id <- is_user$user_id
        session$userData$username <- input$username
      }else{
        session$userData$user_id <- is_user$user_id
        session$userData$username <- input$username
      }
      
      output$userlogin <- renderUI({
        HTML("&nbsp;")
      }) 
    }
  })
  

  
  #userinfo----
  output$userinfo <- renderUI({
    js$getcookie()
    req(input$jscookie)
    tagList(
      tags$small(session$userData$username, "  ", actionLink('logout', '[Logout]'))
    )
  }) 
  
  
  
  #lotlisth----
  output$lotlisth <- renderUI({
    js$getcookie()
    req(input$jscookie)
    
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    #Check for next lot----
    lots_q <- dbSendQuery(db, "SELECT count(*) FROM qc_lots WHERE project_id = ? AND qc_pass IS NULL")
    dbBind(lots_q, list(project_id))
    lots_next <- dbFetch(lots_q)
    dbClearResult(lots_q)
    
    if (lots_next[1,1] == 0){
      create_lot(db)
      
      #runqc_refresh
      HTML("<script>$(location).attr('href', './')</script>")
    }else{
      if(which_folder == "NULL"){
        HTML("<a href=\"./\"><span class=\"glyphicon glyphicon-home\" aria-hidden=\"true\"></span> Home</a><br><br><br><h4>List of folders for QC:</h4>")
      }
    }
  })
  
  
  
  #lotlist1----
  output$lotlist1 <- renderUI({
    js$getcookie()
    req(input$jscookie)
    
    query <- parseQueryString(session$clientData$url_search)
    which_lot <- query['lot_id']
    
    qclots_q <- paste0("SELECT *, array_to_string(qc_lot_dates, ',') AS qc_lot_dates_f FROM qc_lots WHERE project_id = ", project_id, " ORDER BY qc_lot_id DESC")
    flog.info(paste0("qclots_q: ", qclots_q), name = "qc")
    qc_lots <- dbGetQuery(db, qclots_q)
    
    list_of_lots <- ""
    
    if (dim(qc_lots)[1] > 0){

      qc_next = FALSE
              
      for (i in 1:dim(qc_lots)[1]){
        
        if (which_lot != "NULL"){
          if (qc_lots$qc_lot_id[i] == which_lot){
            is_active <- "active"
          }else{
            is_active <- ""
          }
        }else{
          is_active <- ""
        }
        
        if (qc_next == TRUE){
          this_folder <- paste0("<a class=\"list-group-item ", is_active, "\">", qc_lots$qc_lot_title[i])
        }else{
          this_folder <- paste0("<a href=\"./?lot_id=", qc_lots$qc_lot_id[i], "\" class=\"list-group-item ", is_active, "\">", qc_lots$qc_lot_title[i])
        }

        lot_qc_status <- qc_lots$qc_pass[i]
        
        if (is.na(lot_qc_status)){
          this_folder <- paste0(this_folder, " <span class=\"label label-default\" title=\"QC Pending\">QC Pending</span> ")
          if (qc_next == FALSE){
            #qc_next = TRUE
          }
        }else{
          if (lot_qc_status == 1){
            this_folder <- paste0(this_folder, " <span class=\"label label-success\" title=\"Folder passed QC\">QC OK</span> ")
          }else if (lot_qc_status == 0){
            this_folder <- paste0(this_folder, " <span class=\"label label-danger\" title=\"Folder failed QC\">QC Failed</span> ")
          }
        }
        
        this_folder <- paste0(this_folder, "<p>Dates: ", qc_lots$qc_lot_dates_f[i], "</p>")
        this_folder <- paste0(this_folder, "</a>")
        list_of_lots <- paste0(list_of_lots, this_folder)
      }
    }
    
    list_of_lots <- paste0(list_of_lots, "</div><br><br><br>")
    HTML(list_of_lots)
  })
  

  
  #observeEvent_logout----
  observeEvent(input$logout, {
    js$rmcookie()
    #runqc_refresh----
    output$runqc <- renderUI({
      HTML("<script>$(location).attr('href', './')</script>")
    })
  })
  
  
  
  #runqc----
  output$runqc <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    lot_id <- query['lot_id']
    qc <- query['runqc']
    
    if (qc == "NULL"){req(FALSE)}
    
    if (lot_id == "NULL"){req(FALSE)}
    
    q <- paste0("SELECT count(*) as done_files FROM qc_lots_files WHERE qc_lot_id = ", lot_id, " AND qc_critical IS NOT NULL")
    flog.info(paste0("qc_file: ", q), name = "qc")
    done_files <- as.integer(dbGetQuery(db, q)[1,1])
    
    q <- paste0("SELECT count(*) as no_files FROM qc_lots_files WHERE qc_lot_id = ", lot_id)
    flog.info(paste0("qc_file: ", q), name = "qc")
    no_files <- as.integer(dbGetQuery(db, q)[1,1])
    
    percent_done <- done_files/no_files
    
    progress0 <- shiny::Progress$new()
    progress0$set(message = paste0("QC progress for lot: ", done_files, " out of ", no_files, " files"), value = percent_done)
    
    #QC process here
    q <- paste0("SELECT f.*, fs.path FROM files f, folders fs WHERE f.folder_id = fs.folder_id AND f.file_id IN (SELECT file_id FROM qc_lots_files WHERE qc_lot_id = ", lot_id, " AND qc_critical IS NULL ORDER BY RANDOM() LIMIT 1)")
    flog.info(paste0("qc_file: ", q), name = "qc")
    this_file <- dbGetQuery(db, q)
    
    if (dim(this_file)[1] == 0){
      
      progress0$close()
      
      q <- paste0("SELECT * FROM qc_lots WHERE qc_lot_id = ", lot_id)
      flog.info(paste0("qc_lot_final: ", q), name = "qc")
      lot_info <- dbGetQuery(db, q)
      
      q <- paste0("SELECT * FROM qc_settings WHERE project_id = ", project_id)
      flog.info(paste0("qc_lot_final: ", q), name = "qc")
      qc_settings <- dbGetQuery(db, q)
      
      #Critical
      q <- paste0("SELECT count(*) as no_files FROM qc_lots_files WHERE qc_critical = 'f' AND qc_lot_id = ", lot_id)
      flog.info(paste0("qc_lot_final: ", q), name = "qc")
      qc_critical <- as.integer(dbGetQuery(db, q)[1,1])
      
      qc_critical_per <- round(qc_critical/no_files, 2)
      
      lot_qc <- "Passed"
      
      if (qc_critical_per > qc_settings$qc_threshold_critical){
        qc_critical_lot_res <- "Failed"
        qc_critical_lot_res_col <- "danger"
        lot_qc <- "Failed"
      }else{
        qc_critical_lot_res <- "Passed"
        qc_critical_lot_res_col <- "success"
      }
      qc_critical_lot <- paste0("<span class=\"label label-", qc_critical_lot_res_col, "\" title=\"QC Critical ", qc_critical_lot_res, "\">", qc_critical_lot_res, " (", qc_critical_per, "%)</span>")
      
      #Major
      q <- paste0("SELECT count(*) as no_files FROM qc_lots_files WHERE qc_major = 'f' AND qc_lot_id = ", lot_id)
      flog.info(paste0("qc_lot_final: ", q), name = "qc")
      qc_major <- as.integer(dbGetQuery(db, q)[1,1])
      
      qc_major_per <- round(qc_major/no_files, 2)
      
      if (qc_major_per > qc_settings$qc_threshold_major){
        qc_major_lot_res <- "Failed"
        qc_major_lot_res_col <- "danger"
        lot_qc <- "Failed"
      }else{
        qc_major_lot_res <- "Passed"
        qc_major_lot_res_col <- "success"
      }
      qc_major_lot <- paste0("<span class=\"label label-", qc_major_lot_res_col, "\" title=\"QC Critical ", qc_major_lot_res, "\">", qc_major_lot_res, " (", qc_major_per, "%)</span>")
      
      #Minor
      q <- paste0("SELECT count(*) as no_files FROM qc_lots_files WHERE qc_minor = 'f' AND qc_lot_id = ", lot_id)
      flog.info(paste0("qc_lot_final: ", q), name = "qc")
      qc_minor <- as.integer(dbGetQuery(db, q)[1,1])
      
      qc_minor_per <- round(qc_minor/no_files, 2)
      
      if (qc_minor_per > qc_settings$qc_threshold_minor){
        qc_minor_lot_res <- "Failed"
        qc_minor_lot_res_col <- "danger"
        lot_qc <- "Failed"
      }else{
        qc_minor_lot_res <- "Passed"
        qc_minor_lot_res_col <- "success"
      }
      qc_minor_lot <- paste0("<span class=\"label label-", qc_minor_lot_res_col, "\" title=\"QC Critical ", qc_minor_lot_res, "\">", qc_minor_lot_res, " (", qc_minor_per, "%)</span>")
      
      if (lot_qc == "Failed"){
        lot_class <- "danger"
      }else if (lot_qc == "Passed"){
        lot_class <- "success"
      }
      
      tagList(
                 HTML(paste0("<h4>Lot: <strong>", lot_info$qc_lot_title, "</strong><br>Lot QC result: <span class=\"label label-", lot_class, "\">", lot_qc, "</span>")),
                 HTML(paste0("<dl class=\"dl-horizontal\">
                      <dt>Critical Issues:</dt><dd>", qc_critical_lot, "</dd>
                      <dt>Major Issues:</dt><dd>", qc_major_lot, "</dd>
                      <dt>Minor Issues:</dt><dd>", qc_minor_lot, "</dd>
                    </dl></h4>")),
                 textInput("qc_info", "Notes about the lot (optional)"),
                 actionButton("qc_done", "Save Results")
      )
    }else{
      
      q <- paste0("SELECT localpath, share FROM projects_shares WHERE strpos ('", this_file$path, "', localpath) > 0")
      flog.info(paste0("qc_file: ", q), name = "qc")
      localpath <- dbGetQuery(db, q)
      
      if (dim(localpath)[1] > 0){
        localpath <- str_replace(this_file$path, localpath$localpath, paste0(localpath$share, "/"))
        localpath <- gsub("/", "\\\\", localpath)
      }else{
        localpath$localpath <- this_file$path
      }
      
      tagList(
        fluidRow(
          column(width = 3,
                 HTML("<p>Filename: <strong>", this_file$file_name, "</strong>"),
                 p("File timestamp: ", this_file$file_timestamp),
                 shinyWidgets::radioGroupButtons(
                        inputId = "qc_critical", label = "Critical Issues:", 
                        choices = c("Pass", "Fail"), 
                        justified = TRUE, status = "primary",
                        checkIcon = list(yes = icon("ok", lib = "glyphicon"))),
                 shinyWidgets::radioGroupButtons(
                        inputId = "qc_major", label = "Major Issues:", 
                        choices = c("Pass", "Fail"), 
                        justified = TRUE, status = "primary",
                        checkIcon = list(yes = icon("ok", lib = "glyphicon"))),
                 shinyWidgets::radioGroupButtons(
                        inputId = "qc_minor", label = "Minor Issues:", 
                        choices = c("Pass", "Fail"), 
                        justified = TRUE, status = "primary",
                        checkIcon = list(yes = icon("ok", lib = "glyphicon"))),
                 textInput("qc_text", "QC Issues"),
                 disabled(textInput("qc_fileid", "File ID", value = this_file$file_id)),
                 actionButton("qc_submit", "Submit"),
                 HTML("<br><br><br><br><p>Full path of original file: ", localpath, "</p>")
          ),
          column(width = 9,
                 HTML(paste0("<p>Move the mouse over the image to zoom in [<a href=\"http://dpogis.si.edu/mdpp/previewimage?file_id=", this_file$file_id, "\" target = _blank>Open image in a new window</a>]</p>
                          <img id=\"zoom_01\" src = \"http://dpogis.si.edu/mdpp/previewimage?file_id=", this_file$file_id, "\" width = \"860\" height = \"auto\" data-zoom-image=\"http://dpogis.si.edu/mdpp/previewimage?file_id=", this_file$file_id,  "\"/>
                           
                          	<script>
                          	  $('#zoom_01').elevateZoom({
                                    zoomType  : \"lens\",
                                    lensShape : \"circle\",
                                    lensSize  : 360,
                                    scrollZoom: true
                                });
                          </script>
                "))
          )
        )
      )
    }
  })
  
  
  
  #observeEvent_qc_submit-----
  observeEvent(input$qc_submit, {
    
    if (input$qc_critical == "Pass"){
      qc_critical = "True"
    }else{
      qc_critical = "False"
    }
    
    if (input$qc_major == "Pass"){
      qc_major = "True"
    }else{
      qc_major = "False"
    }
    
    if (input$qc_minor == "Pass"){
      qc_minor = "True"
    }else{
      qc_minor = "False"
    }
    
    query <- parseQueryString(session$clientData$url_search)
    lot_id <- query['lot_id']
    
    qc_text <- input$qc_text
    file_id <- input$qc_fileid
    
    query <- paste0("UPDATE qc_lots_files SET qc_critical = '", qc_critical, "', qc_major = '", qc_major, "', qc_minor = '", qc_minor, "', qc_info = '", qc_text, "' WHERE file_id = ", file_id, " AND qc_lot_id = ", lot_id)
    
    flog.info(paste0("query: ", query), name = "dashboard")
    
    n <- dbSendQuery(db, query)
    dbClearResult(n)
    
    #runqc_refresh----
    output$runqc <- renderUI({
      query <- parseQueryString(session$clientData$url_search)
      lot_id <- query['lot_id']
      HTML(paste0("<script>$(location).attr('href', './?lot_id=", lot_id, "&runqc=1')</script>"))
    })
  })
  
  
  
  #observeEvent_qc_done----
  observeEvent(input$qc_done, {
    query <- parseQueryString(session$clientData$url_search)
    lot_id <- query['lot_id']
    
    q <- paste0("SELECT count(*) as no_files FROM qc_lots_files WHERE qc_lot_id = ", lot_id)
    flog.info(paste0("qc_file: ", q), name = "qc")
    no_files <- as.integer(dbGetQuery(db, q)[1,1])
    
    q <- paste0("SELECT * FROM qc_lots WHERE qc_lot_id = ", lot_id)
    flog.info(paste0("qc_lot_final: ", q), name = "qc")
    lot_info <- dbGetQuery(db, q)
    
    q <- paste0("SELECT * FROM qc_settings WHERE project_id = ", project_id)
    flog.info(paste0("qc_lot_final: ", q), name = "qc")
    qc_settings <- dbGetQuery(db, q)
    
    #Critical
    q <- paste0("SELECT count(*) as no_files FROM qc_lots_files WHERE qc_critical = 'f' AND qc_lot_id = ", lot_id)
    flog.info(paste0("qc_lot_final: ", q), name = "qc")
    qc_critical <- as.integer(dbGetQuery(db, q)[1,1])
    
    qc_critical_per <- round(qc_critical/no_files, 2)
    
    lot_qc <- "t"
    
    if (qc_critical_per > qc_settings$qc_threshold_critical){
      lot_qc <- "f"
    }
    
    #Major
    q <- paste0("SELECT count(*) as no_files FROM qc_lots_files WHERE qc_major = 'f' AND qc_lot_id = ", lot_id)
    flog.info(paste0("qc_lot_final: ", q), name = "qc")
    qc_major <- as.integer(dbGetQuery(db, q)[1,1])
    
    qc_major_per <- round(qc_major/no_files, 2)
    
    if (qc_major_per > qc_settings$qc_threshold_major){
      lot_qc <- "f"
    }
    
    #Minor
    q <- paste0("SELECT count(*) as no_files FROM qc_lots_files WHERE qc_minor = 'f' AND qc_lot_id = ", lot_id)
    flog.info(paste0("qc_lot_final: ", q), name = "qc")
    qc_minor <- as.integer(dbGetQuery(db, q)[1,1])
    
    qc_minor_per <- round(qc_minor/no_files, 2)
    
    if (qc_minor_per > qc_settings$qc_threshold_minor){
      lot_qc <- "f"
    }
    
    query <- paste0("UPDATE qc_lots SET qc_pass = '", lot_qc, "', qc_reason = '", input$qc_text, "', qc_approved_by = ", session$userData$user_id, " WHERE qc_lot_id = ", lot_id)
    flog.info(paste0("query: ", query), name = "dashboard")
    n <- dbSendQuery(db, query)
    dbClearResult(n)
    
    #Check if can create new lot
    
    next_lot <- create_lot(db)
    if (next_lot != 0){
      #runqc_refresh
      output$runqc <- renderUI({
        HTML(paste0("<script>$(location).attr('href', './?lot_id=", next_lot, "')</script>"))
      })
    }else{
      #runqc_refresh
      output$runqc <- renderUI({
        HTML("<script>$(location).attr('href', './')</script>")
      })
    }
  })
  
  
  
  #lotqctable----
  output$lotqctable <- DT::renderDataTable({
    query <- parseQueryString(session$clientData$url_search)
    lot_id <- query['lot_id']
    runqc <- query['runqc']
    
    if (runqc == "NULL"){
      runqc = 0
    }
    
    if (lot_id == "NULL"){
      req(FALSE)
    }else{
      if (runqc == 1){
        req(FALSE)
      }
      
      lot_info_q <- paste0("SELECT * FROM qc_lots WHERE qc_lot_id = ", lot_id)
      flog.info(paste0("lot_info_q: ", lot_info_q), name = "qc")
      lot_info <- dbGetQuery(db, lot_info_q)
      if (dim(lot_info)[1] == 0){
        req(FALSE)
      }else{
        HTML(paste0("<h3><span class=\"label label-primary\">", lot_info$qc_lot_title, "</span></h3><p>QC Percentage: ", lot_info$qc_lot_percent))
        
        #ADD check for level and adjust percent and lot dates accordingly
        #check_lot(lot_id, db)
        
        file_count <- dbGetQuery(db, paste0("SELECT count(*) AS no_files FROM qc_lots_files WHERE qc_lot_id = ", lot_id))
        
        if (file_count$no_files == 0){
          #Nothing to QC yet, setup
          add_files_to_lot(lot_id, db)
        }
        
        files_qc <- paste0("SELECT f.file_id, f.file_name FROM qc_lots_files q, files f WHERE f.file_id = q.file_id AND q.qc_lot_id = ", lot_id)
        flog.info(paste0("files_qc: ", files_qc), name = "qc")
        files_qc <- dbGetQuery(db, files_qc)
        
        file_checks_q <- paste0("SELECT project_checks FROM projects WHERE project_id = ", project_id)
        flog.info(paste0("file_checks_q: ", file_checks_q), name = "dashboard")
        file_checks_list <<- dbGetQuery(db, file_checks_q)
        file_checks <- stringr::str_split(file_checks_list, ",")[[1]]
        
        files <- data.frame()
        
        for (i in 1:dim(files_qc)[1]){
          #Manual QC
          fileqc_q <- paste0("SELECT * FROM qc_lots_files WHERE file_id = ", files_qc$file_id[i])
          flog.info(paste0("fileqc_q: ", fileqc_q), name = "dashboard")
          fileqc_res <- dbGetQuery(db, fileqc_q)
          
          fileqc <- "<p><strong>Critical</strong>: "
          
          if (is.na(fileqc_res$qc_critical)){
            fileqc <- paste0(fileqc, "<span class=\"label label-default\">Pending</span>")
          }else if (fileqc_res$qc_critical == 0){
            fileqc <- paste0(fileqc, "<span class=\"label label-danger\">Failed</span>")
          }else if (fileqc_res$qc_critical == 1){
            fileqc <- paste0(fileqc, "<span class=\"label label-success\">Passed</span>")
          }
          
          fileqc <- paste0(fileqc, "<br><strong>Major</strong>: ")
          
          if (is.na(fileqc_res$qc_major)){
            fileqc <- paste0(fileqc, "<span class=\"label label-default\">Pending</span>")
          }else if (fileqc_res$qc_major == 0){
            fileqc <- paste0(fileqc, "<span class=\"label label-danger\">Failed</span>")
          }else if (fileqc_res$qc_major == 1){
            fileqc <- paste0(fileqc, "<span class=\"label label-success\">Passed</span>")
          }
          
          fileqc <- paste0(fileqc, "<br><strong>Minor</strong>: ")
          
          if (is.na(fileqc_res$qc_minor)){
            fileqc <- paste0(fileqc, "<span class=\"label label-default\">Pending</span>")
          }else if (fileqc_res$qc_minor == 0){
            fileqc <- paste0(fileqc, "<span class=\"label label-danger\">Failed</span>")
          }else if (fileqc_res$qc_minor == 1){
            fileqc <- paste0(fileqc, "<span class=\"label label-success\">Passed</span>")
          }
                     
          fileqc <- paste0(fileqc, "</p>")

          #Technical qc
          file_checks_q <- paste0("SELECT file_check, CASE WHEN check_results = 0 THEN 'OK' WHEN check_results = 1 THEN 'Failed' WHEN check_results = 9 THEN 'Pending' END as check_results FROM file_checks WHERE file_id = ", files_qc$file_id[i])
          flog.info(paste0("file_checks_q: ", file_checks_q), name = "dashboard")
          file_checks_list <- dbGetQuery(db, file_checks_q)
          
          checks <- "<p>"
          for (j in seq(1, length(file_checks))){
            checks <- paste0(checks, "<strong>", file_checks_list$file_check[j], "</strong>: ")
            
            if (file_checks_list$check_results[j] == "OK"){
              checks <- paste0(checks, "<span class=\"label label-success\">", file_checks_list$check_results[j], "</span>")
            }else if (file_checks_list$check_results[j] == "Failed"){
              checks <- paste0(checks, "<span class=\"label label-danger\">", file_checks_list$check_results[j], "</span>")
            }else if (file_checks_list$check_results[j] == "Pending"){
              checks <- paste0(checks, "<span class=\"label label-default\">", file_checks_list$check_results[j], "</span>")
            }
            checks <- paste0(checks, "<br>")
          }
          checks <- paste0(checks, "</p>")
          
          files <- rbind(files, cbind(files_qc$file_name[i], checks, fileqc, fileqc_res$qc_info, paste0("<a href = \"http://dpogis.si.edu/mdpp/previewimage?file_id=", files_qc$file_id[i], "\" target = \"_blank\"><img src = \"http://dpogis.si.edu/mdpp/previewimage?file_id=", files_qc$file_id[i], "\" width = \"100px\" height = \"auto\"></a>")))
        }
        
        names(files) <- c("Filename", "Technical QC", "QC", "Notes", "Preview (Click to open)")
        files <<- files
        no_rows <- dim(files)[1]
        
        DT::datatable(
          files, 
          escape = FALSE, 
          options = list(
            searching = FALSE, 
            ordering = TRUE, 
            pageLength = no_rows, 
            paging = FALSE,
            dom = 't'
          ),
          rownames = FALSE, 
          selection = 'none')
      }
    }
  })
  
  
  
  #tableheading ----
  output$tableheading <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    lot_id <- query['lot_id']
    
    qc <- query['runqc']
    
    if (qc != "NULL"){
      req(FALSE)
    }
    
    if (lot_id != "NULL"){
      
      lot <- dbGetQuery(db, paste0("SELECT l.*, array_to_string(l.qc_lot_dates, ',') AS qc_lot_dates_f, u.username FROM qc_lots l LEFT JOIN qc_users u ON (l.qc_approved_by = u.user_id) WHERE l.qc_lot_id = ", lot_id))
      
      if (is.na(lot$qc_pass)){
        lotqc_pass <- "<span class=\"label label-default\">QC Pending</span></dd>"
        lotqc_pass_by <- ""
        qc_todo <- paste0("<h2><a href=\"./?runqc=1&lot_id=", lot_id, "\" class=\"btn btn-primary\" role=\"button\">Run QC</a></h2>")
      }else if (lot$qc_pass == 0){
        lotqc_pass <- "<span class=\"label label-danger\">Failed</span></dd>"
        lotqc_pass_by <- lot$username
        qc_todo <- ""
      }else if (lot$qc_pass == 1){
        lotqc_pass <- "<span class=\"label label-success\">Passed</span></dd>"
        lotqc_pass_by <- lot$username
        qc_todo <- ""
      }
      
      tagList(
        fluidRow(
          column(width = 9,
                 HTML(qc_todo),
                 HTML(paste0("<h3>", lot$qc_lot_title)),
                 HTML(paste0("<br>Dates: ", lot$qc_lot_dates_f, "</h3>"))
          ),
          column(width = 3,
                 HTML(paste0("<p>", lotqc_pass)),
                 HTML(paste0("<br>Approved by: ", lotqc_pass_by, "</h3>"))
          )
        )
      )
    }
  })
  


  
  
  #footer----
  output$footer <- renderUI({
      HTML(paste0("<h4 style=\"position: fixed; bottom: -10px; width: 100%; padding: 10px; background: white;\"> <a href=\"http://dpo.si.edu\" target = _blank><img src=\"dpologo.jpg\" width = \"238\" height=\"50\"></a> | ", app_name, " ver. ", app_ver, " | <a href=\"", github_link, "\" target = _blank>Source code</a></h4>"))
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
