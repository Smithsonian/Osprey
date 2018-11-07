# Libraries ----
library(shiny)
library(shinydashboard)
library(dplyr)
library(DBI)


source("settings.R")

app_name <- "MassDigi FileCheck Dashboard"
app_ver <- "0.1"
# github_link <- "https://github.com/Smithsonian/dpo_shiny/tree/master/botany_locality"


#Connect to the database
db <- dbConnect(RPostgres::Postgres(), dbname = pg_db,
                 host = pg_host, port = 5432,
                 user = pg_user, password = pg_pass)
#rm(pg_pass) # removes the password

project <- dbGetQuery(db, paste0("SELECT * FROM project_info WHERE project_id = ", project_id))
proj_name <- project$name

dbDisconnect(db)
# unlink("tmp.sqlite3")


# UI ----
ui <- dashboardPage(
  #header
  dashboardHeader(title = proj_name),
  #Sidebar
  dashboardSidebar(disable = TRUE),
  #Body
  dashboardBody(
    
    fluidRow(
      valueBoxOutput("boxred"),
      valueBoxOutput("boxgreen"),
      valueBoxOutput("box")
      ),
    fluidRow(
      column(width = 2,
             box(
               title = "Folders", width = NULL, solidHeader = TRUE, status = "primary",
               uiOutput("boxleft")
             )
        ),
      column(width = 6,
             box(
               title = "Folder details", width = NULL, solidHeader = TRUE, status = "primary",
               uiOutput("folderinfo"),
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
    
    #footer
    hr(),
    uiOutput("footer")
  )
)


# Server ----
server <- function(input, output, session) {

  #Connect to the database
  db <- dbConnect(RPostgres::Postgres(), dbname = pg_db,
                  host = pg_host, port = 5432,
                  user = pg_user, password = pg_pass)
  
  output$boxred <- renderValueBox({
    
    status_query <- paste0("SELECT e.count_error, o.count_ok, t.count_total FROM 
                            (SELECT count(*) AS count_error FROM files where (file_pair = 1 OR jhove = 1 OR tif_size = 1 OR raw_size = 1 OR iptc_metadata = 1 OR magick = 1 OR unique_file = 1) and folder_id in (select folder_id from folders where project_id = ", project_id, ")) e,
                            (SELECT count(*) AS count_ok FROM files where (file_pair + jhove + iptc_metadata + tif_size + raw_size + iptc_metadata + magick + unique_file) = 0 and folder_id in (select folder_id from folders where project_id = ", project_id, ")) o,
                            (SELECT count(*) AS count_total FROM files WHERE folder_id in (select folder_id from folders where project_id = ", project_id, ")) t"
    )
    #cat(status_query)
    files_status <<- dbGetQuery(db, status_query)
    
    if (files_status$count_total == 0){
      valueBox(
        "NA", "Files with errors", icon = icon("exclamation-sign", lib = "glyphicon"),
        color = "red"
      )
    }else{
      valueBox(
        paste0(round((files_status$count_error/files_status$count_total) * 100, 1), " %"), paste0(files_status$count_error, " files with errors"), icon = icon("exclamation-sign", lib = "glyphicon"),
        color = "red"
      )
    }
    
  })
  
  
  
  
  
  output$boxgreen <- renderValueBox({
    if (files_status$count_total == 0){
      valueBox(
        "NA", "Files OK", icon = icon("ok-sign", lib = "glyphicon"),
        color = "green"
      )
    }else{
      valueBox(
        paste0(round((files_status$count_ok/files_status$count_total) * 100, 1), " %"), paste0(files_status$count_ok, " files OK"), icon = icon("ok-sign", lib = "glyphicon"),
        color = "green"
      )
    }
  })
    
  
  
  
  output$box <- renderValueBox({
    valueBox(
      files_status$count_total, "Total Files", icon = icon("file", lib = "glyphicon"),
      color = "blue"
    )
  })
    
  

  
  
  #boxleft----
  output$boxleft <- renderUI({
    
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    folders <- dbGetQuery(db, paste0("SELECT project_folder, folder_id FROM folders WHERE project_id = ", project_id, " ORDER BY project_folder DESC"))
    
    #list_of_folders <- "<h3><a href=\"./\">Reload</a></h3><br><br><div class=\"list-group\">"
    list_of_folders <- "<div class=\"list-group\">"
    
    if (dim(folders)[1] == 0){
      
    }else{
      for (i in 1:dim(folders)[1]){
        
        if (folders$project_folder[i] == which_folder){
          this_folder <- paste0("<a href=\"./?folder=", folders$folder_id[i], "\" class=\"list-group-item active\">", folders$project_folder[i])
        }else{
          this_folder <- paste0("<a href=\"./?folder=", folders$folder_id[i], "\" class=\"list-group-item\">", folders$project_folder[i])
        }
        
        folder_subdirs <- dbGetQuery(db, paste0("SELECT status from folders where folder_id = ", folders$folder_id[i]))
        if (folder_subdirs == 9){
          this_folder <- paste0(this_folder, " <span class=\"label label-danger\" title=\"Missing subfolders\">Error</span> ")
        }
        
        count_files <- paste0("SELECT count(*) as no_files from files where folder_id = ", folders$folder_id[i])
        #cat(count_files)
        folder_files <- dbGetQuery(db, count_files)
        this_folder <- paste0(this_folder, " <span class=\"badge\" title=\"No. of files\">", folder_files$no_files, "</span> ")
        
        #Only if there are any files
        if (folder_files$no_files > 0){
          error_files <- dbGetQuery(db, paste0("SELECT count(*) AS count_error FROM files WHERE folder_id = ", folders$folder_id[i], " AND (file_pair = 1 OR jhove = 1 OR tif_size = 1 OR raw_size = 1 OR iptc_metadata = 1 OR magick = 1 OR unique_file = 1)"))
          
          if (error_files == 0){
            this_folder <- paste0(this_folder, " <span class=\"label label-success\">OK</span> ")
          }else if (error_files > 0){
            this_folder <- paste0(this_folder, " <span class=\"label label-danger\" title=\"Files with errors\">Error</span> ")
          }
          md5_file <- dbGetQuery(db, paste0("SELECT md5 FROM folders WHERE folder_id = ", folders$folder_id[i]))[1]
          #cat(md5_file$md5)
          if (md5_file$md5 != 0){
            this_folder <- paste0(this_folder, " <span class=\"label label-warning\" title=\"Missing MD5 file\">MD5</span> ")
          }
        }else{
          this_folder <- paste0(this_folder, " <span class=\"label label-default\" title=\"No files in folder\">Empty</span> ")
        }
        
        unknown_file <- dbGetQuery(db, paste0("SELECT status FROM folders WHERE folder_id = ", folders$folder_id[i]))
        if (unknown_file$status == 1){
          this_folder <- paste0(this_folder, " <span class=\"label label-warning\" title=\"Unknown file found in folder\">Unknown File</span> ")
        }
        
        this_folder <- paste0(this_folder, "</a>")
        
        list_of_folders <- paste0(list_of_folders, this_folder)
      }
    }
    
    
    
    list_of_folders <- paste0(list_of_folders, "</div>")
    
    HTML(list_of_folders)
  })
  
  
  
  
  
  
  #folderinfo----
  output$folderinfo <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    
    if (which_folder == "NULL"){
      p("Select a folder from the list on the left")
    }else{
      
      folder_info <- dbGetQuery(db, paste0("SELECT * FROM folders WHERE folder_id = ", which_folder))
      
      #Only if there are any files
      this_folder <- ""
     
      folder_subdirs <- dbGetQuery(db, paste0("SELECT status, error_info from folders where folder_id = '", which_folder, "'"))
      error_msg <- ""
      if (folder_subdirs$status == 9){
        error_msg <- paste0("<h4><span class=\"label label-danger\" title=\"Missing subfolders\">", folder_subdirs$error_info, "</span></h4>")
      }
      
      tagList(
        fluidRow(
          column(width = 4,
                 h4(folder_info$project_folder)
          ),
          column(width = 8,
                 # em(folder_info$path),
                 # tags$br(),
                 em(folder_info$notes),
                 br(),
                 HTML(error_msg)
          )#,
          # column(width = 4,
          #        HTML(this_folder)
          # )
        ),
        hr()
      )
    }
  })
  
  
  
  
  
  
  output$files_table <- DT::renderDataTable({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    req(which_folder != "NULL")
    
    #files_data <<- dbGetQuery(db, paste0("SELECT file_name, file_pair, jhove, iptc_metadata, file_size, magick_identify, unique_file FROM collection_items WHERE project_folder = '", which_folder, "' ORDER BY file_name"))
    files_data <<- dbGetQuery(db, paste0("SELECT file_id, file_name, file_pair, jhove, tif_size, raw_size, magick, unique_file FROM files WHERE folder_id = '", which_folder, "' ORDER BY file_name"))
    
    DT::datatable(
          files_data, 
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
            '0: OK, 1: error, 9: not checked'
          )
          ) %>% DT::formatStyle(
            'file_pair',
            backgroundColor = DT::styleEqual(c(0, 1, 9), c('#00a65a', '#dd4b39', '#A9A9A9'))
          ) %>% DT::formatStyle(
            'jhove',
            backgroundColor = DT::styleEqual(c(0, 1, 9), c('#00a65a', '#dd4b39', '#A9A9A9'))
          # ) %>% DT::formatStyle(
          #   'iptc_metadata',
          #   backgroundColor = DT::styleEqual(c(0, 1, 9), c('#00a65a', '#dd4b39', '#A9A9A9'))
          ) %>% DT::formatStyle(
            'tif_size',
            backgroundColor = DT::styleEqual(c(0, 1, 9), c('#00a65a', '#dd4b39', '#A9A9A9'))
          ) %>% DT::formatStyle(
            'raw_size',
            backgroundColor = DT::styleEqual(c(0, 1, 9), c('#00a65a', '#dd4b39', '#A9A9A9'))
          ) %>% DT::formatStyle(
            'magick',
            backgroundColor = DT::styleEqual(c(0, 1, 9), c('#00a65a', '#dd4b39', '#A9A9A9'))
          ) %>% DT::formatStyle(
            'unique_file',
            backgroundColor = DT::styleEqual(c(0, 1, 9), c('#00a65a', '#dd4b39', '#A9A9A9'))
          )
    
  })
  
  
  
  
  
  #fileinfo----
  output$fileinfo <- renderUI({
    query <- parseQueryString(session$clientData$url_search)
    which_folder <- query['folder']
    req(which_folder != "NULL")
    
    req(input$files_table_rows_selected)
    
    file_info <- dbGetQuery(db, paste0("SELECT * FROM files WHERE file_id = ", files_data[input$files_table_rows_selected, ]$file_id))
    print(input$files_table_rows_selected)
    html_to_print <- "<dl class=\"dl-horizontal\">"
    
    html_to_print <- paste0(html_to_print, "<dt>File name</dt><dd>", file_info$file_name, "</dd>")
    html_to_print <- paste0(html_to_print, "<dt>Accession No.</dt><dd>", file_info$accession_no, "</dd>")
    
    if (!is.na(file_info$file_pair_info[1])){
      if (file_info$file_pair[1] == 0){
        html_to_print <- paste0(html_to_print, "<dt>File pair</dt><dd>", file_info$file_pair_info, "</dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>File pair</dt><dd class=\"bg-danger\">", file_info$file_pair_info, "</dd>")
      }
    }
  
  
    if (!is.na(file_info$iptc_metadata_info[1])){
      if (file_info$iptc_metadata[1] == 0){
        html_to_print <- paste0(html_to_print, "<dt>IPTC metadata</dt><dd>", file_info$iptc_metadata_info, "</dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>IPTC metadata</dt><dd class=\"bg-danger\">", file_info$iptc_metadata_info, "</dd>")
      }
    }
  
    if (!is.na(file_info$tif_size_info[1])){
      if (file_info$tif_size[1] == 0){
        html_to_print <- paste0(html_to_print, "<dt>TIF file size</dt><dd>", file_info$tif_size_info, "</dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>TIF file size</dt><dd class=\"bg-danger\">", file_info$tif_size_info, "</dd>")
      }
    }
    
    if (!is.na(file_info$raw_size_info[1])){
      if (file_info$raw_size[1] == 0){
        html_to_print <- paste0(html_to_print, "<dt>RAW file size</dt><dd>", file_info$raw_size_info, "</dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>RAW file size</dt><dd class=\"bg-danger\">", file_info$raw_size_info, "</dd>")
      }
    }
  
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
    
    if (!is.na(file_info$magick_info[1])){
      if (file_info$magick[1] == 0){
        html_to_print <- paste0(html_to_print, "<dt>Imagemagick</dt><dd><pre>", file_info$magick_info, "</pre></dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>Imagemagick</dt><dd class=\"bg-danger\"><pre>", file_info$magick_info, "</pre></dd>")
      }
    }
    
    if (!is.na(file_info$jhove_info[1])){
      if (file_info$jhove[1] == 0){
        html_to_print <- paste0(html_to_print, "<dt>JHOVE</dt><dd>", file_info$jhove_info, "</dd>")
      }else{
        html_to_print <- paste0(html_to_print, "<dt>JHOVE</dt><dd class=\"bg-danger\">", file_info$jhove_info, "</dd>")
      }
    }
    
    html_to_print <- paste0(html_to_print, "</dl>")
    HTML(html_to_print)
  })
  
  
  
  
  #footer----
  output$footer <- renderUI({
    HTML(paste0("<h4 style=\"position: fixed; bottom: -10px; width: 100%; text-align: right; right: 0px; padding: 10px; background: white;\">", app_name, " ver. ", app_ver, " | <a href=\"http://dpo.si.edu\" target = _blank><img src=\"dpologo.jpg\" width = \"238\" height=\"50\"></a></h4>"))
  })
  
}



# Run app ----
shinyApp(ui = ui, server = server, onStart = function() {
  cat("Loading\n")
  #load project's info
  #Mount path
  onStop(function() {
    cat("Closing\n")
    #Close databases
    try(dbDisconnect(db), silent = TRUE)
    cat("Removing objects\n")
    rm(list = ls())
  })
})
