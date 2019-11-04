# Packages ----
library(shiny)
library(dplyr)
library(DBI)
library(DT)
library(futile.logger)
library(reshape)
library(stringr)
library(shinycssloaders)
library(shinyjs)



# Settings ----
source("settings.R")
app_name <- "Osprey QC"
app_ver <- "0.1.0"
github_link <- "https://github.com/Smithsonian/MDFileCheck"

options(stringsAsFactors = FALSE)
options(encoding = 'UTF-8')

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

dbDisconnect(db)

#addResourcePath("js", "www")

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
  
  # tags$head(
  #   tags$style(HTML("
  #     #folder_id {
  #       display: none;
  #     }"))
  # ),
  
  tags$head(
    tags$script(src = "js.cookie.min.js")
  ),
  useShinyjs(),
  extendShinyjs(text = jsCode),
  
  #ImageZoom scripts
  tags$script(src = "imgViewer.min.js"),
  tags$script(src = "jquery.mousewheel.min.js"),
  tags$link(rel = "stylesheet", type = "text/css", href = "imgViewer.min.css"),
  tags$script(src = "image_zoom.js"),
  #Add class zoomimage to image to zoom in
  
  #header
  titlePanel(proj_name),
  #Body
  #User login
  fluidRow(
    column(width = 3,
           br()
    ),
    column(width = 6,
           uiOutput("userlogin")
    ),
    column(width = 3,
           uiOutput("userinfo"),
           #verbatimTextOutput("output"),
           br()
    )
  ),
  uiOutput("folderlisth"),
  fluidRow(
    column(width = 3,
           uiOutput("folderlist1")
    )
  ),
  uiOutput("tableheading"),
  DT::dataTableOutput("folderqc"),
  uiOutput("passfail"),
  #Footer
  hr(),
  uiOutput("footer")
)


# Server ----
server <- function(input, output, session) {
  
  #cat(session$userData)
  
  
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
  
  
  
  #Connect to the database ----
  if (Sys.info()["nodename"] == "shiny.si.edu"){
    #For RHEL7 odbc driver
    pg_driver = "PostgreSQL"
  }else{
    #Ubuntu odbc driver
    pg_driver = "PostgreSQL Unicode"
  }
  
  db <- dbConnect(odbc::odbc(),
                  driver = pg_driver,
                  database = pg_db,
                  uid = pg_user,
                  pwd = pg_pass,
                  server = pg_host,
                  port = 5432)

  
  
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
  
  
  # output$output <- renderText({
  #   paste0('You are logged ', status())}
  # )
  
  
  #userlogin----
  output$userlogin <- renderUI({
    js$getcookie()
    if (is.null(input$jscookie)){
      tagList(
        br(),br(),br(),br(),
        textInput("username", "Username:", value = 'villanueval'),
        passwordInput("password", "Password:", value = 'qccontrol'),
        actionButton("login", "Login")
      )
    }else{
      user_id <- dbGetQuery(db, paste0("SELECT c.user_id, u.username FROM qc_users_cookies c, qc_users u WHERE c.user_id = u.user_id AND u.project_id = ", project_id, " AND c.cookie = '", input$jscookie, "'"))
      #cat(dim(user_id)[1])
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
  
  
  observeEvent(input$login, {
    is_user <- dbGetQuery(db, paste0("SELECT user_id FROM qc_users WHERE project_id = ", project_id, " AND username = '", input$username, "' AND pass = MD5('", input$password, "')"))
    if (dim(is_user)[1] == 0){
      output$userlogin <- renderUI({
        p("Error: User not found or password not correct.")
      }) 
    }else{
      user_id <- dbGetQuery(db, paste0("SELECT c.user_id FROM qc_users_cookies c, qc_users u WHERE c.user_id = u.user_id AND u.project_id = ", project_id, " AND c.cookie = '", input$jscookie, "'"))
      #cat(dim(user_id)[1])
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
      p(session$userData$username),
      actionButton('logout', 'Logout')
    )
  }) 
  
  
  #folderlisth----
  output$folderlisth <- renderUI({
    js$getcookie()
    req(input$jscookie)
    
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    if(which_folder == "NULL"){
      HTML("<br><h4>List of folders for QC:</h4>")
    }
  })
  
  
  #folderlist1----
  output$folderlist1 <- renderUI({
    js$getcookie()
    req(input$jscookie)
    
    query <- parseQueryString(session$clientData$url_search)
    which_lot <- query['lot_id']
    
    #if(which_lot == "NULL"){
      #None selected, show all
      qclots_q <- paste0("SELECT *, array_to_string(qc_lot_dates, ',') AS qc_lot_dates_f FROM qc_lots WHERE project_id = ", project_id, " ORDER BY qc_lot_date ASC")
      flog.info(paste0("qclots_q: ", qclots_q), name = "qc")
      qc_lots <- dbGetQuery(db, qclots_q)
      
      list_of_lots <- ""
      
      if (dim(qc_lots)[1] > 0){
        
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
          
          this_folder <- paste0("<a href=\"./?lot_id=", qc_lots$qc_lot_id[i], "\" class=\"list-group-item ", is_active, "\">", qc_lots$qc_lot_title[i])
          
          lot_qc_status <- qc_lots$qc_pass[i]
          
          if (is.na(lot_qc_status)){
            this_folder <- paste0(this_folder, " <span class=\"label label-default\" title=\"QC Pending\">QC Pending</span> ")
          }else{
            if (lot_qc_status == 0){
              this_folder <- paste0(this_folder, " <span class=\"label label-success\" title=\"Folder passed QC\">QC OK</span> ")
            }else if (lot_qc_status == 1){
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
  
  
  observeEvent(input$logout, {
    js$rmcookie()
  })
  
  
  #folderqc----
  output$folderqc <- DT::renderDataTable({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    if (which_folder == "NULL"){
      req(FALSE)
    }else{
      
      folder_info_q <- paste0("SELECT f.*, qc.qc_status, qc.qc_percent FROM folders f LEFT JOIN folders_qc qc ON f.folder_id = qc.folder_id WHERE f.folder_id = ", which_folder)
      flog.info(paste0("folder_info_q: ", folder_info_q), name = "qc")
      folder_info <- dbGetQuery(db, folder_info_q)
      if (dim(folder_info)[1] == 0){
        req(FALSE)
      }else{
        HTML(paste0("<h3><span class=\"label label-primary\">", folder_info$project_folder, "</span></h3><p>Local path: ", folder_info$path, "</p><p>QC Percentage: ", folder_info$qc_percent))
        
        file_count <- dbGetQuery(db, paste0("SELECT count(*) AS no_files FROM folders_qc_files WHERE folder_id = ", which_folder))
        
        if (file_count$no_files == 0){
          #Nothing to QC yet, setup
          qc_percent_q <- paste0("SELECT qc_percent FROM folders_qc WHERE folder_id = ", which_folder)
          flog.info(paste0("qc_percent_q: ", qc_percent_q), name = "qc")
          qc_percent <- dbGetQuery(db, qc_percent_q)
          
          qc_files_q <- paste0("SELECT count(*) as no_files FROM files WHERE folder_id = ", which_folder)
          flog.info(paste0("qc_files_q: ", qc_files_q), name = "qc")
          qc_files <- dbGetQuery(db, qc_files_q)
          
          qc_limit <- ceiling(as.integer(qc_files$no_files) * (as.integer(qc_percent$qc_percent)/100))
          
          qc_q <- paste0("INSERT INTO folders_qc_files (folder_id, file_id) (SELECT folder_id, file_id FROM files WHERE folder_id = ", which_folder, " ORDER BY RANDOM() LIMIT ", qc_limit, ")")
          flog.info(paste0("qc_q: ", qc_q), name = "qc")
          n <- dbSendQuery(db, qc_q)
          dbClearResult(n)
        }
        
        files_qc <- paste0("SELECT f.file_id, f.file_name FROM folders_qc_files q, files f WHERE f.file_id = q.file_id AND q.folder_id = ", which_folder)
        flog.info(paste0("files_qc: ", files_qc), name = "qc")
        files_qc <- dbGetQuery(db, files_qc)
        
        file_checks_q <- paste0("SELECT project_checks FROM projects WHERE project_id = ", project_id)
        flog.info(paste0("file_checks_q: ", file_checks_q), name = "dashboard")
        file_checks_list <<- dbGetQuery(db, file_checks_q)
        file_checks <- stringr::str_split(file_checks_list, ",")[[1]]
        
        files <- data.frame()
        
        for (i in 1:dim(files_qc)[1]){
          file_checks_q <- paste0("SELECT file_check, CASE WHEN check_results = 0 THEN 'OK' WHEN check_results = 1 THEN 'Failed' WHEN check_results = 9 THEN 'Pending' END as check_results FROM file_checks WHERE file_id = ", files_qc$file_id[i])
          flog.info(paste0("file_checks_q: ", file_checks_q), name = "dashboard")
          file_checks_list <- dbGetQuery(db, file_checks_q)
          
          checks <- "<dl class=\"dl-horizontal\">"
          for (j in seq(1, length(file_checks))){
            checks <- paste0(checks, "<dt>", file_checks_list$file_check[j], "</dt><dd>")
            
            if (file_checks_list$check_results[j] == "OK"){
              checks <- paste0(checks, "<span class=\"label label-success\">", file_checks_list$check_results[j], "</span></dd>")
            }else if (file_checks_list$check_results[j] == "Failed"){
              checks <- paste0(checks, "<span class=\"label label-danger\">", file_checks_list$check_results[j], "</span></dd>")
            }else if (file_checks_list$check_results[j] == "Pending"){
              checks <- paste0(checks, "<span class=\"label label-default\">", file_checks_list$check_results[j], "</span></dd>")
            }
            
          }
          checks <- paste0(checks, "</dl>")
          
          files <- rbind(files, cbind(files_qc$file_name[i], checks, paste0("<img src = \"http://dpogis.si.edu/mdpp/previewimage?file_id=", files_qc$file_id[i], "\" width = \"160px\" height = \"auto\"> <a href = \"http://dpogis.si.edu/mdpp/previewimage?file_id=", files_qc$file_id[i], "\" target = \"_blank\">[Open image]</a>")))
        }
        
        names(files) <- c("Filename", "Checks", "Preview")
        
        files <<- files
        
        no_rows <- dim(files)[1]
        
        DT::datatable(
          files, 
          #class = c('compact', 'table-stripe', 'table-hover'),
          escape = FALSE, 
          options = list(
            searching = FALSE, 
            ordering = FALSE, 
            pageLength = no_rows, 
            paging = FALSE,
            dom = 't'
          ),
          rownames = FALSE, 
          selection = 'multiple')
      }
    }
  })
  
  
  
  #tableheading ----
  output$tableheading <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    if (which_folder != "NULL"){
      
      folder <- dbGetQuery(db, paste0("SELECT *, to_char(date, 'Mon DD, YYYY') as date_f FROM folders WHERE folder_id = ", which_folder))
      
      tagList(
        fluidRow(
          column(width = 10,
                 HTML(paste0("<h4><a href=\"./\"><span class=\"glyphicon glyphicon-home\" aria-hidden=\"true\"></span> List of folders for QC</a></h4>")),
                 h3(folder$project_folder),
                 HTML(paste0("<p>Local path: ", folder$path)),
                 HTML(paste0("<p>Date: ", folder$date_f))
          ),
          column(width = 2,
                 uiOutput("goback")
          )
        ),
        h4("Click on rows with errors, if any")
      )
      
    }
  })
  
  
  #passfail----
  output$passfail <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    if(which_folder == "NULL"){
      req(FALSE)
    }
    
    tagList(
      br(),
      fluidRow(
        column(width = 3,
               textInput("folder_id", "", value = which_folder),
               textInput("user", "User:"),
               passwordInput("password", "Password:"),
               br(),
               br(),
               br(),
               HTML(paste0("<h4><a href=\"./\"><span class=\"glyphicon glyphicon-home\" aria-hidden=\"true\"></span> List of folders for QC</a></h4>")),
               br(),
               br(),
               br()
        ),
        column(width = 3,
               radioButtons("qc_status_f", "QC Results:", 
                            choiceNames = list(
                              HTML("<p><span class=\"label label-danger\">Folder failed QC</span>"),
                              HTML("<p><span class=\"label label-success\">Folder passed QC</span>")
                            ),
                            choiceValues = c("1", "0")),
               textAreaInput("qc_reason", "Reasons for failure:", value = if(!is.null(input$folderqc_rows_selected)){paste0("\n\n\nFiles with issues: ", paste(files[input$folderqc_rows_selected, ]$Filename, collapse = ","))}else{""}, rows = 4),
               actionButton("submitqc", "Submit"),
               br(),
               br(),
               br()
        ),
        column(width = 6,
               uiOutput("message"),
               DT::dataTableOutput("folderhist")
        )
      )
    )
  })
  
  
  observeEvent(input$submitqc, {
    
    check_user_q <- paste0("SELECT count(*) AS user_found FROM qc_users WHERE project_id = ", project_id, " AND username = '", input$user, "' AND pass = MD5('", input$password, "') AND user_active = 't'")
    check_user <- dbGetQuery(db, check_user_q)
      
    if (check_user == 1){
      
      insert_q <- paste0("INSERT INTO folders_qc 
                          (folder_id, qc_status, qc_reason, qc_approved_by) 
                        VALUES 
                          (", input$folder_id, ", ", input$qc_status_f, ", '", input$qc_reason, "', '", input$user, "')")
      n <- dbSendQuery(db, insert_q)
      dbClearResult(n)
      
      output$message <- renderUI({
        HTML("<div class=\"alert alert-success\" role=\"alert\">QC results saved.</div>")
      })
      
    }else{
      output$message <- renderUI({
        HTML("<div class=\"alert alert-danger\" role=\"alert\">Username or password error.</div>")
      })
    }
    
    #folderhist----
    output$folderhist <- DT::renderDataTable({
      query <- parseQueryString(session$clientData$url_search)
      which_folder <- query['folder']
      
      if(which_folder == "NULL"){
        req(FALSE)
      }
      
      folder_hist <- dbGetQuery(db, paste0("SELECT CASE WHEN qc_status = 0 THEN 'Pass' WHEN qc_status = 1 THEN 'Failed' END as qc_status, qc_percent, qc_approved_by, qc_reason, TO_CHAR(updated_at, 'Mon dd, yyyy HH:MM:SS') as timestamp FROM folders_qc WHERE qc_status != 9 AND folder_id = ", which_folder))
      
      no_rows <- dim(folder_hist)[1]
      
      if (no_rows > 0){
        
        names(folder_hist) <- c("Status", "QC Percent", "QC Approved by", "Text of issues", "Timestamp")
        
        DT::datatable(
          folder_hist, 
          class = c('compact'),
          escape = FALSE, 
          options = list(
            searching = FALSE, 
            ordering = FALSE, 
            pageLength = no_rows, 
            paging = FALSE,
            dom = 't'
          ),
          rownames = FALSE, 
          selection = 'none')
      }
    })
    
  })
  #folderhist----
  output$folderhist <- DT::renderDataTable({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    if(which_folder == "NULL"){
      req(FALSE)
    }
    
    folder_hist <- dbGetQuery(db, paste0("SELECT CASE WHEN qc_status = 0 THEN 'Pass' WHEN qc_status = 1 THEN 'Failed' END as qc_status, qc_percent, qc_approved_by, qc_reason, TO_CHAR(updated_at, 'Mon dd, yyyy HH:MM:SS') as timestamp FROM folders_qc WHERE qc_status != 9 AND folder_id = ", which_folder))
    
    no_rows <- dim(folder_hist)[1]
    
    if (no_rows > 0){
      
      names(folder_hist) <- c("Status", "QC Percent", "QC Approved by", "Text of issues", "Timestamp")
      
      DT::datatable(
        folder_hist, 
        class = c('compact'),
        escape = FALSE, 
        options = list(
          searching = FALSE, 
          ordering = FALSE, 
          pageLength = no_rows, 
          paging = FALSE,
          dom = 't'
        ),
        rownames = FALSE, 
        selection = 'none')
    }
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
