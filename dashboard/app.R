# Packages ----
library(shiny)
library(shinydashboard)
library(dplyr)
library(DBI)
library(RPostgres)
library(DT)



# Settings ----
source("settings.R")
app_name <- "MassDigi FileCheck Dashboard"
app_ver <- "0.3.3"
github_link <- "https://github.com/Smithsonian/MDFileCheck"


#Connect to the database ----
db <- dbConnect(RPostgres::Postgres(), dbname = pg_db,
                 host = pg_host, port = 5432,
                 user = pg_user, password = pg_pass)

project <- dbGetQuery(db, paste0("SELECT * FROM projects WHERE project_id = ", project_id))
proj_name <- project$project_acronym

dbDisconnect(db)



# UI ----
ui <- dashboardPage(
  #header ----
  dashboardHeader(title = proj_name),
  #Sidebar----
  dashboardSidebar(disable = TRUE),
  #Body----
  dashboardBody(
    fluidRow(
      valueBoxOutput("box_ok", width = 3),
      valueBoxOutput("box_error", width = 3),
      valueBoxOutput("itemcount", width = 3),
      valueBoxOutput("totalbox", width = 3)
      ),
    fluidRow(
      column(width = 2,
             box(
               title = "Folders", width = NULL, solidHeader = TRUE, status = "primary",
               uiOutput("folderlist")
             )
        ),
      column(width = 6,
             box(
               title = "Folder details", width = NULL, solidHeader = TRUE, status = "primary",
               uiOutput("folderinfo"),
               uiOutput("tableheading"),
               DT::dataTableOutput("files_table")
             )
      ),
      column(width = 4,
             box(
               title = "File details", width = NULL, solidHeader = TRUE, status = "primary",
               uiOutput("fileinfo")
             )
      )
    ),
    #Footer ----
    hr(),
    uiOutput("footer")
  )
)


# Server ----
server <- function(input, output, session) {

  #Connect to the database ----
  db <- dbConnect(RPostgres::Postgres(), dbname = pg_db,
                  host = pg_host, port = 5432,
                  user = pg_user, password = pg_pass)
  
  file_checks_list <<- dbGetQuery(db, paste0("SELECT project_checks FROM projects WHERE project_id = ", project_id))
  file_checks <- stringr::str_split(file_checks_list, ",")[[1]]
  
  #Box_error ----
  output$box_error <- renderValueBox({
    status_query <- "SELECT e.count_error, o.count_ok, t.count_total, i.item_count FROM
                            (SELECT count(*) AS count_error FROM files where ("
    
    for (f in 1:length(file_checks)){
      status_query <- paste0(status_query, file_checks[f], " = 1 OR ")
    }
    
    status_query <- stringr::str_sub(status_query, 0, -5)
    status_query <- paste0(status_query, ") and 
                    folder_id in (select folder_id from folders where project_id = ", project_id, ")) e,
                    (SELECT count(*) AS count_ok FROM files where (")
    
    for (f in 1:length(file_checks)){
      status_query <- paste0(status_query, file_checks[f], " + ")
    }
    
    status_query <- stringr::str_sub(status_query, 0, -4)
    status_query <- paste0(status_query, ") = 0 and folder_id in (select folder_id from folders where project_id = ", project_id, ")) o,
                            (SELECT count(*) AS count_total FROM files WHERE folder_id in (select folder_id from folders where project_id = ", project_id, ")) t,
                           (SELECT count(DISTINCT item_no) as item_count FROM files WHERE folder_id in (select folder_id from folders where project_id = ", project_id, ")) i")
    
    files_status <<- dbGetQuery(db, status_query)
    
    if (files_status$count_total == 0){
      err_files_count <- "NA"
      err_files_subtitle <- "Files with errors"
    }else{
      err_files_count <- paste0(round((files_status$count_error/files_status$count_total) * 100, 1), " %")
      err_files_subtitle <- paste0(files_status$count_error, " files with errors")
    }
    valueBox(
      err_files_count, err_files_subtitle, icon = icon("exclamation-sign", lib = "glyphicon"),
      color = "red"
    )
  })
  
  
  
  
  #box_ok ----
  output$box_ok <- renderValueBox({
    if (files_status$count_total == 0){
      ok_files_count <- "NA"
      ok_files_subtitle <- "Files OK"
    }else{
      ok_files_count <- paste0(round((files_status$count_ok/files_status$count_total) * 100, 1), " %")
      ok_files_subtitle <- paste0(files_status$count_ok, " files OK")
    }
    valueBox(
      ok_files_count, ok_files_subtitle, icon = icon("ok-sign", lib = "glyphicon"),
      color = "green"
    )
  })
    
  
  #Itemcount----
  output$itemcount <- renderValueBox({
    valueBox(
      files_status$item_count, "No. of Items", icon = icon("file", lib = "glyphicon"),
      color = "blue"
    )
  })
  
  
  
  #Totalbox----
  output$totalbox <- renderValueBox({
    valueBox(
      files_status$count_total, "No. of Images", icon = icon("picture", lib = "glyphicon"),
      color = "teal"
    )
  })
    
  

  
  
  #folderlist----
  output$folderlist <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    folders <- dbGetQuery(db, paste0("SELECT project_folder, folder_id FROM folders WHERE project_id = ", project_id, " ORDER BY date DESC, project_folder DESC"))
    
    #Only display if it is an active project, from settings
    if (project_active == TRUE){
      last_update <- as.numeric(dbGetQuery(db, "SELECT 
                            to_char(NOW() - max(last_update), 'SS')
                             AS last_update FROM
                        (SELECT max(updated_at) AS last_update FROM folders
                        UNION
                        SELECT max(last_update) AS last_update FROM files)
                        a"))
      
      if (last_update > 180){
        last_update_m <- ceiling(last_update / 3)
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
    
    list_of_folders <- paste0("<p><strong><a href=\"./\"><span class=\"glyphicon glyphicon-home\" aria-hidden=\"true\"></span> Home</a></strong></p>", last_update_text, "<br><div class=\"list-group\">")
    
    if (dim(folders)[1] > 0){
      for (i in 1:dim(folders)[1]){
        
        if (as.character(folders$folder_id[i]) == as.character(which_folder)){
          this_folder <- paste0("<a href=\"./?folder=", folders$folder_id[i], "\" class=\"list-group-item active\">", folders$project_folder[i], "<p class=\"list-group-item-text\">")
        }else{
          this_folder <- paste0("<a href=\"./?folder=", folders$folder_id[i], "\" class=\"list-group-item\">", folders$project_folder[i], "<p class=\"list-group-item-text\">")
        }
        
        folder_subdirs <- dbGetQuery(db, paste0("SELECT status from folders where folder_id = ", folders$folder_id[i]))
        if (folder_subdirs == 9){
          this_folder <- paste0(this_folder, "<span class=\"label label-danger\" title=\"Missing subfolders\">Error</span> ")
        }
        
        count_files <- paste0("SELECT count(*) as no_files from files where folder_id = ", folders$folder_id[i])
        folder_files <- dbGetQuery(db, count_files)
        this_folder <- paste0(this_folder, " <span class=\"badge pull-right\" title=\"No. of files\">", folder_files$no_files, "</span> ")
        
        #Only if there are any files
        if (folder_files$no_files > 0){
          error_files_query <- paste0("SELECT count(*) AS count_error FROM files WHERE folder_id = ", folders$folder_id[i], " AND (")
          
          for (f in 1:length(file_checks)){
            error_files_query <- paste0(error_files_query, file_checks[f], " = 1 OR ")
          }
          
          error_files_query <- stringr::str_sub(error_files_query, 0, -5)
          error_files_query <- paste0(error_files_query, ")")
          error_files <- dbGetQuery(db, error_files_query)
          if (error_files == 0){
            #Check if all have been checked
            checked_files_query <- paste0("SELECT count(*) AS count_checked FROM files WHERE folder_id = ", folders$folder_id[i], " AND (")
            
            for (f in 1:length(file_checks)){
              checked_files_query <- paste0(checked_files_query, file_checks[f], " = 9 OR ")
            }
            
            checked_files_query <- stringr::str_sub(checked_files_query, 0, -5)
            checked_files_query <- paste0(checked_files_query, ")")
            checked_files <- dbGetQuery(db, checked_files_query)
            if (checked_files == 0){
              this_folder <- paste0(this_folder, " <span class=\"label label-success\" title=\"Files passed validation tests\">OK</span> ")
            }
            
          }else if (error_files > 0){
            this_folder <- paste0(this_folder, " <span class=\"label label-danger\" title=\"Files with errors\">Error</span> ")
          }
          
          #MD5 ----
          if (stringr::str_detect(file_checks_list, "jpg")){
            md5_file <- dbGetQuery(db, paste0("SELECT md5_tif + md5_jpg as md5 FROM folders WHERE folder_id = ", folders$folder_id[i]))
          }else{
            md5_file <- dbGetQuery(db, paste0("SELECT md5_tif + md5_raw as md5 FROM folders WHERE folder_id = ", folders$folder_id[i]))
          }
          
          if ((md5_file$md5 > 0)){
            this_folder <- paste0(this_folder, " <span class=\"label label-warning\" title=\"Missing MD5 file\">MD5</span> ")
          }
        }else{
          this_folder <- paste0(this_folder, " <span class=\"label label-default\" title=\"No files in folder\">Empty</span> ")
        }
        
        unknown_file <- dbGetQuery(db, paste0("SELECT status FROM folders WHERE folder_id = ", folders$folder_id[i]))
        if (unknown_file$status == 1){
          this_folder <- paste0(this_folder, " <span class=\"label label-warning\" title=\"Unknown file found in folder\">Unknown File</span> ")
        }
        
        this_folder <- paste0(this_folder, "</p></a>")
        
        list_of_folders <- paste0(list_of_folders, this_folder)
      }
    }
    
    list_of_folders <- paste0(list_of_folders, "</div>")
    HTML(list_of_folders)
  })
  
  
  
  
  
  
  #Folderinfo----
  output$folderinfo <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    if (which_folder == "NULL"){
      p("Select a folder from the list on the left")
    }else{
      
      folder_info <- dbGetQuery(db, paste0("SELECT *, to_char(timestamp, 'Mon DD, YYYY HH24:MI:SS') as import_date, to_char(updated_at, 'Mon DD, YYYY HH24:MI:SS') as updated_at_formatted FROM folders WHERE folder_id = ", which_folder))
      if (dim(folder_info)[1] == 0){
        p("Select a folder from the list on the left")
      }else{
        this_folder <- ""
        
        folder_subdirs <- dbGetQuery(db, paste0("SELECT status, error_info from folders where folder_id = '", which_folder, "'"))
        error_msg <- ""
        if (folder_subdirs$status == 9){
          error_msg <- paste0("<h4><span class=\"label label-danger\" title=\"Missing subfolders\">", folder_subdirs$error_info, "</span></h4>")
        }
        
        #tif md5
        if (folder_info$md5_tif != 0){
          error_msg <- paste0(error_msg, " <span class=\"label label-warning\" title=\"Missing TIF MD5 file\">Missing TIF MD5 file</span> ")
        }
        
        if (stringr::str_detect(file_checks_list, "jpg")){
          #jpg md5
          if (folder_info$md5_jpg != 0){
            error_msg <- paste0(error_msg, " <span class=\"label label-warning\" title=\"Missing JPG MD5 file\">Missing JPG MD5 file</span> ")
          }
        }else{
          #raw md5
          if (folder_info$md5_raw != 0){
            error_msg <- paste0(error_msg, " <span class=\"label label-warning\" title=\"Missing RAW MD5 file\">Missing RAW MD5 file</span> ")
          }
        }
        
        tagList(
          fluidRow(
            column(width = 6,
                   HTML(paste0("<h3><span class=\"label label-primary\">", folder_info$project_folder, "</span></h3>"))
            ),
            column(width = 6,
                   if (!is.na(folder_info$notes)){
                     p(em(folder_info$notes))},
                   p("Folder imported on: ", folder_info$import_date, br(), "Last update on: ", folder_info$updated_at_formatted),
                   HTML(error_msg)
            )
          ),
          hr()
        )
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
    
    folder_info <- dbGetQuery(db, paste0("SELECT *, to_char(timestamp, 'Mon DD, YYYY HH24:MI:SS') as import_date FROM folders WHERE folder_id = ", which_folder))
    if (dim(folder_info)[1] == 0){
      req(FALSE)
    }
    
    files_data <<- dbGetQuery(db, paste0("SELECT file_id, file_name, ", file_checks_list, " FROM files WHERE folder_id = '", which_folder, "' ORDER BY file_timestamp DESC"))
    files_data_table <- dbGetQuery(db, paste0("SELECT file_name, ", file_checks_list, " FROM files WHERE folder_id = '", which_folder, "' ORDER BY file_timestamp DESC"))
    
    no_cols <- dim(files_data_table)[2]
    
    DT::datatable(
          files_data_table, 
          escape = FALSE, 
          options = list(
                searching = TRUE, 
                ordering = TRUE, 
                pageLength = 50, 
                paging = TRUE, 
                language = list(zeroRecords = "Folder has no files yet")
              ), 
          rownames = FALSE, 
          selection = 'single',
          caption = htmltools::tags$caption(
            style = 'caption-side: bottom; text-align: center;',
            'Codes: 0 = OK, 1 = error, 9 = not checked yet'
          )) %>% DT::formatStyle(
            2:no_cols,
            backgroundColor = DT::styleEqual(c(0, 1, 9), c('#00a65a', '#d9534f', '#777')),
            color = 'white'
          )
  })
  
  
  
  
  
  #Fileinfo ----
  output$fileinfo <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    req(which_folder != "NULL")
    
    req(input$files_table_rows_selected)
    
    file_info <- dbGetQuery(db, paste0("SELECT *, to_char(timestamp, 'Mon DD, YYYY HH24:MI:SS') as date, to_char(file_timestamp, 'Mon DD, YYYY HH24:MI:SS') as filedate FROM files WHERE file_id = ", files_data[input$files_table_rows_selected, ]$file_id))
    print(input$files_table_rows_selected)
    
    file_id <- files_data[input$files_table_rows_selected, ]$file_id
    
    html_to_print <- "<h4>File info</h4><dl class=\"dl-horizontal\">"
    html_to_print <- paste0(html_to_print, "<dt>File name</dt><dd>", file_info$file_name, "</dd>")
    html_to_print <- paste0(html_to_print, "<dt>File ID</dt><dd>", file_info$file_id, "</dd>")
    html_to_print <- paste0(html_to_print, "<dt>Item number</dt><dd>", file_info$item_no, "</dd>")
    html_to_print <- paste0(html_to_print, "<dt>File timestamp</dt><dd>", file_info$filedate, "</dd>")
    html_to_print <- paste0(html_to_print, "<dt>Imported on</dt><dd>", file_info$date, "</dd>")
    
    if (!is.null(file_info$tif_md5)){
      html_to_print <- paste0(html_to_print, "<dt>TIF MD5</dt><dd>", file_info$tif_md5, "</dd>")
    }
    
    if (!is.null(file_info$raw_md5)){
      html_to_print <- paste0(html_to_print, "<dt>RAW MD5</dt><dd>", file_info$raw_md5, "</dd>")
    }
    
    #if JPG, show md5
    if (stringr::str_detect(file_checks_list, "jpg")){
      html_to_print <- paste0(html_to_print, "<dt>JPG MD5</dt><dd>", file_info$jpg_md5, "</dd>")
    }
      
    #file_pair ----
    if (stringr::str_detect(file_checks_list, "file_pair")){
      if (!is.na(file_info$file_pair_info[1])){
        if (file_info$file_pair[1] == 0){
          html_to_print <- paste0(html_to_print, "<dt>File pair</dt><dd>", file_info$file_pair_info, "</dd>")
        }else{
          html_to_print <- paste0(html_to_print, "<dt>File pair</dt><dd class=\"bg-danger\">", file_info$file_pair_info, "</dd>")
        }
      }
    }
  
    #itpc ----
    if (stringr::str_detect(file_checks_list, "itpc")){
      if (!is.na(file_info$iptc_metadata_info[1])){
        if (file_info$iptc_metadata[1] == 0){
          html_to_print <- paste0(html_to_print, "<dt>IPTC metadata</dt><dd>", file_info$iptc_metadata_info, "</dd>")
        }else{
          html_to_print <- paste0(html_to_print, "<dt>IPTC metadata</dt><dd class=\"bg-danger\">", file_info$iptc_metadata_info, "</dd>")
        }
      }
    }
  
    #tif_size ----
    if (stringr::str_detect(file_checks_list, "tif_size")){
      if (!is.na(file_info$tif_size_info[1])){
        if (file_info$tif_size[1] == 0){
          html_to_print <- paste0(html_to_print, "<dt>TIF file size</dt><dd>", file_info$tif_size_info, "</dd>")
        }else{
          html_to_print <- paste0(html_to_print, "<dt>TIF file size</dt><dd class=\"bg-danger\">", file_info$tif_size_info, "</dd>")
        }
      }
    }
    
    #raw_size ----
    if (stringr::str_detect(file_checks_list, "raw_size")){
      if (!is.na(file_info$raw_size_info[1])){
        if (file_info$raw_size[1] == 0){
          html_to_print <- paste0(html_to_print, "<dt>RAW file size</dt><dd>", file_info$raw_size_info, "</dd>")
        }else{
          html_to_print <- paste0(html_to_print, "<dt>RAW file size</dt><dd class=\"bg-danger\">", file_info$raw_size_info, "</dd>")
        }
      }
    }
  
    #unique_file ----
    if (stringr::str_detect(file_checks_list, "unique_file")){
      if (file_info$unique_file[1] > 0){
        other_folders <- dbGetQuery(db, paste0("SELECT project_folder FROM files WHERE file_name = '", files_data[input$files_table_rows_selected, ]$file_name, "' AND folder_id != ", which_folder," AND folder_id in (select folder_id from folders where project_id = ", project_id, ")"))
        if (dim(other_folders)[1] > 0){
          html_to_print <- paste0(html_to_print, "<dt>Duplicate</dt><dd class=\"bg-danger\">")
          for (j in 1:dim(other_folders)[1]){
            html_to_print <- paste0(html_to_print, "", other_folders$project_folder, "<br>")
          }
          html_to_print <- paste0(html_to_print, "</dd>")
        }
      }
    }

    #JHOVE ----
    if (stringr::str_detect(file_checks_list, "jhove")){
      if (!is.na(file_info$jhove_info[1])){
        if (file_info$jhove[1] == 0){
          html_to_print <- paste0(html_to_print, "<dt>JHOVE</dt><dd>", file_info$jhove_info, "</dd>")
        }else{
          html_to_print <- paste0(html_to_print, "<dt>JHOVE</dt><dd class=\"bg-danger\">", file_info$jhove_info, "</dd>")
        }
      }
    }
    
    #JPG ----
    if (stringr::str_detect(file_checks_list, "jpg")){
      if (file_info$jpg[1] == 1){
        html_to_print <- paste0(html_to_print, "<dt>JPG validation</dt><dd class=\"bg-danger\">Failed</dd><dt>JPG Imagemagick details</dt><dd class=\"bg-danger\"><pre>", file_info$jpg_info, "</pre></dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>JPG validation</dt><dd>OK</dd>")
      }
    }
    
    #tifpages ----
    if (stringr::str_detect(file_checks_list, "tifpages")){
      if (file_info$tifpages[1] == 1){
        html_to_print <- paste0(html_to_print, "<dt>Multiple pages in TIF</dt><dd class=\"bg-danger\">Failed, there are multiple pages in the TIF</dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>Multiple pages in TIF</dt><dd>No</dd>")
      }
    }
    
    #ImageMagick ----
    if (stringr::str_detect(file_checks_list, "magick")){
      if (!is.na(file_info$magick_info[1])){
        if (file_info$magick[1] == 0){
          html_to_print <- paste0(html_to_print, "<dt>Imagemagick validation</dt><dd>OK</dd><dt>Imagemagick details</dt><dd><pre>", file_info$magick_info, "</pre></dd>")
        }else{
          html_to_print <- paste0(html_to_print, "<dt>Imagemagick validation</dt><dd class=\"bg-danger\">Failed</dd><dt>Imagemagick details</dt><dd class=\"bg-danger\"><pre>", file_info$magick_info, "</pre></dd>")
        }
      }
    }
    
    html_to_print <- paste0(html_to_print, "</dl>")
    
    #Image preview ----
    if (stringr::str_detect(file_checks_list, "jpg")){
      #JPG's are taken, show these
      tagList(
        fluidRow(
          column(width = 6,
                 HTML(paste0("<p>TIF preview:</p><a href=\"previews/", stringr::str_sub(file_id, 1, 2), "/", file_id, ".jpg\" target = _blank><img src = \"previews/", stringr::str_sub(file_id, 1, 2), "/", file_id, ".jpg\" width = \"160px\" height = \"auto\"></a><br>"))
          ),
          column(width = 6,
                 HTML(paste0("<p>JPG preview:</p><a href=\"previews/", stringr::str_sub(file_id, 1, 2), "/", file_id, "_jpg.jpg\" target = _blank><img src = \"previews/", stringr::str_sub(file_id, 1, 2), "/", file_id, "_jpg.jpg\" width = \"160px\" height = \"auto\"></a><br>"))
          )
        ),
        hr(),
        HTML(html_to_print)
      )
    }else{
      #Only display the preview of the TIF
      tagList(
        fluidRow(
          column(width = 12,
                 HTML(paste0("<p>TIF preview:</p><a href=\"previews/", stringr::str_sub(file_id, 1, 2), "/", file_id, ".jpg\" target = _blank><img src = \"previews/", stringr::str_sub(file_id, 1, 2), "/", file_id, ".jpg\" width = \"160px\" height = \"auto\"></a><br>"))
          )
        ),
        hr(),
        HTML(html_to_print)
      )
    }
  })
  
  
  
  
  #Footer ----
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
    rm(list = ls())
  })
})
