#!/usr/bin/env python3

import psycopg2
import psycopg2.extras
import settings
import sys
import edan
import requests


if len(sys.argv) == 1:
    print("folder_id missing")
elif len(sys.argv) == 2:
    folder_id = sys.argv[1]
elif len(sys.argv) == 3:
    folder_id = sys.argv[1]
    # Botany: NMNHBOTANY
    keywords = sys.argv[2]
else:
    print("Wrong number of args")


try:
    conn = psycopg2.connect(host=settings.host, database=settings.database, user=settings.user,
                            password=settings.password)
except psycopg2.Error as e:
    print('System error')
    sys.exit(1)

cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
conn.autocommit = True


data = cur.execute("select file_id, file_name from files where folder_id = %(folder_id)s", {'folder_id': folder_id})

rows = cur.fetchall()

print("Number of rows: {}".format(len(rows)))
i = 1

for row in rows:
    print("Working row {} - file_id: {}".format(i, row['file_id']))
    i += 1
    results = edan.searchEDAN("{} {}".format(row['file_name'], keywords), settings.AppID, settings.AppKey)
    if results['rowCount'] == 1:
        try:
            media = results['rows'][0]['content']['descriptiveNonRepeating']['online_media']['media'][0]['idsId']
            if media[:4] == 'ark:':
                d = cur.execute(
                    "UPDATE files SET preview_image = %(preview_image)s WHERE file_id = %(file_id)s",
                    {
                        'file_id': row['file_id'],
                        'preview_image': 'https://ids.si.edu/ids/deliveryService/id/{}'.format(media)
                    })
            else:
                d = cur.execute(
                    "UPDATE files SET preview_image = %(preview_image)s WHERE file_id = %(file_id)s",
                    {
                        'file_id': row['file_id'],
                        'preview_image': media
                    })
        except:
            try:
                media = results['rows'][0]['url']
                if media[:4] == 'dams':
                    media = media.replace('damsmdm:', '')
                    ids_media = 'https://ids.si.edu/ids/deliveryService/id/{}'.format(media)
                    r = requests.head(ids_media)
                    if r.status_code == 200:
                        d = cur.execute(
                            "UPDATE files SET preview_image = %(preview_image)s WHERE file_id = %(file_id)s",
                            {
                                'file_id': row['file_id'],
                                'preview_image': ids_media
                            })
                    else:
                        print("media not found")
            except:
                print("media not found")
        try:
            ark = results['rows'][0]['content']['descriptiveNonRepeating']['guid']
        except:
            ark = results['rows'][0]['content']['ead_ref_id']
        if ark[:10] == 'http://n2t':
            ark_id = ark.replace('http://n2t.net/', '')
            link_url = ark
            link_name="Collection Record"
            iiif_manifest = "https://ids.si.edu/ids/manifest/{}".format(ark_id)
            iiif = "https://iiif.si.edu/mirador/?manifest=https://ids.si.edu/ids/manifest/{}".format(ark_id)
            d = cur.execute(
                "delete from files_links where file_id = %(file_id)s and link_name = %(link_name)s",
                {
                    'file_id': row['file_id'],
                    'link_name': link_name
                })
            d = cur.execute(
                "insert into files_links (file_id, link_name, link_url) values (%(file_id)s, %(link_name)s, %(link_url)s)", {
                'file_id': row['file_id'],
                'link_name': link_name,
                'link_url': link_url,
            })
        else:
            link_url = "https://sova.si.edu/search/digital?q={}".format(ark)
            iiif_manifest = "https://ids.si.edu/ids/manifest/{}".format(ark)
            iiif = "https://iiif.si.edu/mirador/?manifest=https://ids.si.edu/ids/manifest/{}".format(ark)
            link_name = 'Collection Record'
            d = cur.execute(
                "delete from files_links where file_id = %(file_id)s and link_name = %(link_name)s",
                {
                    'file_id': row['file_id'],
                    'link_name': link_name
                })
            # d = cur.execute(
            #     "insert into files_links (file_id, link_name, link_url) values (%(file_id)s, %(link_name)s, %(link_url)s)", {
            #     'file_id': row['file_id'],
            #     'link_name': link_name,
            #     'link_url': link_url,
            # })
        r = requests.head(iiif_manifest)
        if r.status_code == 404:
            iiif_manifest = "https://ids.si.edu/ids/manifest/{}".format(media)
            iiif = "https://iiif.si.edu/mirador/?manifest=https://ids.si.edu/ids/manifest/{}".format(media)
            r = requests.head(iiif_manifest)
        if r.status_code == 200:
            # IIIF
            link_name = '<img src="/static/logo-iiif.png">'
            d = cur.execute(
                "delete from files_links where file_id = %(file_id)s and link_name = %(link_name)s",
                {
                    'file_id': row['file_id'],
                    'link_name': link_name
                })
            d = cur.execute(
                "insert into files_links (file_id, link_name, link_url) values (%(file_id)s, %(link_name)s, %(link_url)s)",
                {
                    'file_id': row['file_id'],
                    'link_name': link_name,
                    'link_url': iiif
                })
            # IIIF
            link_name = 'IIIF Manifest'
            d = cur.execute(
                "delete from files_links where file_id = %(file_id)s and link_name = %(link_name)s",
                {
                    'file_id': row['file_id'],
                    'link_name': link_name
                })
            d = cur.execute(
                "insert into files_links (file_id, link_name, link_url) values (%(file_id)s, %(link_name)s, %(link_url)s)",
                {
                    'file_id': row['file_id'],
                    'link_name': link_name,
                    'link_url': iiif_manifest
                })



cur.close()
conn.close()

