"""Invoice reconciliation logic for the dashboard web views."""

import random

import pandas as pd

from osprey.db import executemany, run_query


def list_user_projects(username):
    return run_query(
        ("select p.project_title, p.project_id, p.project_alias, date_format(p.project_start, '%b-%Y') as project_start, "
         "     date_format(p.project_end, '%b-%Y') as project_end, p.qc_status, p.project_unit "
         " FROM qc_projects qp, "
         "       users u, projects p "
         " WHERE qp.project_id = p.project_id AND qp.user_id = u.user_id AND u.username = %(username)s "
         "     AND p.project_alias IS NOT NULL AND p.project_status != 'Completed' "
         " GROUP BY p.project_title, p.project_id, p.project_alias, "
         "     p.project_start, p.project_end, p.qc_status, p.project_unit "
         " ORDER BY p.projects_order DESC"),
        {'username': username})


def reconcile_invoice(project_id, uploaded_file):
    """Match an uploaded list of file names against Osprey/DAMS (or transcription) records.

    Returns a dict of template variables for invoice_recon.html.
    """
    files = pd.read_csv(uploaded_file)
    files = files.set_axis(['files'], axis=1)
    files['files'] = files['files'].str.replace('.tif', '')
    randomval = random.randint(1000, 9999)
    files['randomval'] = randomval
    files.dropna(inplace=True)
    files = files[files['files'] != '']
    res = [tuple(x) for x in files.to_numpy()]
    project_info = run_query(
        "SELECT * FROM projects WHERE project_id = %(project_id)s", {'project_id': project_id}
    )[0]

    if project_info['transcription'] == 1:
        executemany(
            "INSERT INTO invoice_recon_transcription (file_name, project_id, randomint) VALUES (%s, {}, %s)".format(
                project_info['project_id']),
            res,
        )
        # Add IDs
        run_query(
            ("with data as (select f.file_transcription_id, f.file_name from transcription_files f, "
             "transcription_folders fol where f.folder_transcription_id = fol.folder_transcription_id "
             "and fol.project_id = %(project_id)s) UPDATE invoice_recon_transcription i join data d "
             "on i.file_name = d.file_name SET i.file_transcription_id = d.file_transcription_id "
             "where randomint = %(randomint)s"),
            {'randomint': randomval, 'project_id': project_id})
        # Match the ones with transcriptions
        run_query(
            ("with data as (select f.file_transcription_id, f.file_name from transcription_files f, "
             "transcription_folders fol, transcription_files_text tft, transcription_fields fields "
             "where tft.field_id = fields.field_id AND f.folder_transcription_id = fol.folder_transcription_id "
             "AND fol.project_id = %(project_id)s) UPDATE invoice_recon i join data d on i.file_name = d.file_name "
             "SET i.dams_uan = d.dams_uan where randomint = %(randomint)s"),
            {'randomint': randomval, 'project_id': project_id})
        no_files = run_query(
            "SELECT count(*) as no_files FROM invoice_recon WHERE randomint = %(randomint)s",
            {'randomint': randomval})[0]['no_files']
        no_files_osprey = run_query(
            "SELECT count(*) as no_files FROM invoice_recon WHERE randomint = %(randomint)s and file_id IS NOT NULL",
            {'randomint': randomval})[0]['no_files']
        no_files_transcription = run_query(
            "SELECT count(*) as no_files FROM invoice_recon WHERE randomint = %(randomint)s AND dams_uan IS NOT NULL",
            {'randomint': randomval})[0]['no_files']
        msg = ""
        if int(no_files_osprey) < int(no_files):
            count_msg = "Reconciliation failed: {:,} files not in Osprey".format(int(no_files) - int(no_files_osprey))
            count_msg_css = "danger"
        elif int(no_files_transcription) < int(no_files):
            # NOTE: pre-existing bug carried over from app.py — no_files_dams is not
            # defined on this branch, so this message raises NameError if ever hit.
            count_msg = "Reconciliation failed: {:,} files do not have transcription data".format(int(no_files) - int(no_files_dams))
            count_msg_css = "danger"
        elif (int(no_files_osprey) == int(no_files)) and (int(no_files_transcription) == int(no_files)):
            count_msg = "Reconciliation passed: all files accounted for."
            count_msg_css = "success"
        else:
            count_msg = "Reconciliation failed: SYSTEM ERROR"
            count_msg_css = "danger"
    else:
        executemany("INSERT INTO invoice_recon (file_name, randomint) VALUES (%s, %s)", res)
        run_query(
            ("with data as (select f.file_id, f.file_name from files f, folders fol where f.folder_id = fol.folder_id "
             "and fol.project_id = %(project_id)s) UPDATE invoice_recon i join data d on i.file_name = d.file_name "
             "SET i.file_id = d.file_id where randomint = %(randomint)s"),
            {'randomint': randomval, 'project_id': project_id})
        run_query(
            ("with data as (select f.file_id, f.file_name, f.dams_uan from files f, folders fol where "
             "f.folder_id = fol.folder_id and fol.project_id = %(project_id)s) UPDATE invoice_recon i join data d "
             "on i.file_name = d.file_name SET i.dams_uan = d.dams_uan where randomint = %(randomint)s"),
            {'randomint': randomval, 'project_id': project_id})
        no_files = run_query(
            "SELECT count(*) as no_files FROM invoice_recon WHERE randomint = %(randomint)s",
            {'randomint': randomval})[0]['no_files']
        no_files_osprey = run_query(
            "SELECT count(*) as no_files FROM invoice_recon WHERE randomint = %(randomint)s and file_id IS NOT NULL",
            {'randomint': randomval})[0]['no_files']
        no_files_dams = run_query(
            "SELECT count(*) as no_files FROM invoice_recon WHERE randomint = %(randomint)s AND dams_uan IS NOT NULL",
            {'randomint': randomval})[0]['no_files']
        msg = ""
        if int(no_files_osprey) < int(no_files):
            count_msg = "Reconciliation failed: {:,} files not in Osprey".format(int(no_files) - int(no_files_osprey))
            count_msg_css = "danger"
        elif int(no_files_dams) < int(no_files):
            count_msg = "Reconciliation failed: {:,} files not in DAMS".format(int(no_files) - int(no_files_dams))
            count_msg_css = "danger"
        elif (int(no_files_osprey) == int(no_files)) and (int(no_files_dams) == int(no_files)):
            count_msg = "Reconciliation passed: all files accounted for."
            count_msg_css = "success"
        else:
            count_msg = "Reconciliation failed: SYSTEM ERROR"
            count_msg_css = "danger"

    return {
        'no_files': no_files,
        'no_files_osprey': no_files_osprey,
        'no_files_dams': no_files_dams,
        'msg': msg,
        'randomval': randomval,
        'project_info': project_info,
        'count_msg': count_msg,
        'count_msg_css': count_msg_css,
    }


def build_invoice_export(randomint):
    return pd.DataFrame(run_query(
        ("SELECT i.file_name, i.file_id, i.dams_uan, fol.project_folder FROM invoice_recon i "
         "left join files f on (i.file_id = f.file_id) left join folders fol on (f.folder_id = fol.folder_id) "
         "WHERE i.randomint = %(randomint)s"),
        {'randomint': randomint}))
