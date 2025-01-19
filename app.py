import random
import openai
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import os
import re

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
openai.api_key = api_key

def validate_playlist_rules(data, num_playlists, tracks_per_playlist):
    """Validate if the playlists can be created based on the rules."""
    unique_artists = data['artist'].nunique()
    total_tracks = len(data)

    max_tracks_by_artist = 3 * unique_artists * num_playlists
    if total_tracks < tracks_per_playlist * num_playlists:
        return False, "Error: Archivo con data menor a tus solicitud. Ajusta la cantidad de playlists y tracks e intentalo de nuevo."
    if max_tracks_by_artist < tracks_per_playlist * num_playlists:
        return False, "Too many restrictions for the available tracks."
    return True, "Valid playlist configuration."

def generate_playlists(data, num_playlists, tracks_per_playlist):
    """Generate playlists based on the rules."""
    playlists = []
    used_isrcs = set()  # Track ISRCs globally across all playlists

    for _ in range(num_playlists):
        playlist = []
        used_artists = {}
        remaining_tracks = data.copy()

        while len(playlist) < tracks_per_playlist:
            valid_tracks = remaining_tracks[~remaining_tracks['artist'].isin(
                [artist for artist, count in used_artists.items() if count >= 3]
            ) & ~remaining_tracks['isrc'].isin(used_isrcs)]

            if valid_tracks.empty:
                break

            if 'streams' in valid_tracks.columns:
                valid_tracks = valid_tracks.copy()  # Prevent SettingWithCopyWarning
                valid_tracks['weight'] = valid_tracks['streams'] / valid_tracks['streams'].sum()
                selected_track = valid_tracks.sample(1, weights='weight').iloc[0]
            else:
                # If no 'streams' column, select randomly
                selected_track = valid_tracks.sample(1).iloc[0]

            # Ensure no consecutive tracks by the same artist
            if playlist and playlist[-1]['artist'] == selected_track['artist']:
                continue

            playlist.append(selected_track)

            # Update artist usage, used ISRCs, and remaining tracks
            artist = selected_track['artist']
            used_artists[artist] = used_artists.get(artist, 0) + 1
            used_isrcs.add(selected_track['isrc'])
            remaining_tracks = remaining_tracks[remaining_tracks['isrc'] != selected_track['isrc']]

        playlist_df = pd.DataFrame(playlist)
        playlist_df['Exclude from Excel'] = False
        playlists.append(playlist_df)
    return playlists

def save_preliminary_excel(playlists, output_filename):
    """Save playlists to a preliminary Excel file with editable columns."""
    with pd.ExcelWriter(output_filename) as writer:
        for i, playlist in enumerate(playlists):
            playlist['#'] = range(1, len(playlist) + 1)  # Add numbering for easy exclusion
            sheet_name = f"Playlist {i + 1}"[:31]
            playlist.to_excel(writer, sheet_name=sheet_name, index=False)

def process_edited_excel(file):
    """Process the edited Excel to generate the final playlists."""
    try:
        excel_data = pd.ExcelFile(file)
        playlists = []

        for sheet_name in excel_data.sheet_names:
            playlist = pd.read_excel(excel_data, sheet_name=sheet_name)
            if 'Exclude from Excel' in playlist.columns:
                playlist = playlist[~playlist['Exclude from Excel']]
            playlists.append(playlist)

        return "Playlists processed successfully!", playlists
    except Exception as e:
        return f"Error processing the edited Excel file: {e}", None

# Streamlit Interface
st.title("Playlist Generator")
st.write("Generate a preliminary Excel file to edit playlists and process the final result.")

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])
num_playlists = st.number_input("Number of Playlists", min_value=1, value=3, step=1)
tracks_per_playlist = st.number_input("Tracks per Playlist", min_value=1, value=20, step=1)

if st.button("Generate Preliminary Excel"):
    if uploaded_file is not None:
        with st.spinner("Generating playlists..."):
            data = pd.read_excel(uploaded_file, sheet_name=0)
            required_columns = ['Recording Artist', 'Recording Title', 'ISRC']
            optional_columns = ['Number of Streams']

            if not all(col in data.columns for col in required_columns):
                st.error("The uploaded file does not contain the required columns. Please check your file and try again.")
            else:
                data = data[required_columns + [col for col in optional_columns if col in data.columns]]
                data.rename(columns={
                    'Recording Artist': 'artist',
                    'Recording Title': 'title',
                    'ISRC': 'isrc',
                    'Number of Streams': 'streams'
                }, inplace=True)
                data.dropna(inplace=True)

                is_valid, message = validate_playlist_rules(data, num_playlists, tracks_per_playlist)
                if not is_valid:
                    st.error(message)
                else:
                    playlists = generate_playlists(data, num_playlists, tracks_per_playlist)
                    output_filename = "Preliminary_Playlists.xlsx"
                    save_preliminary_excel(playlists, output_filename)

                    with open(output_filename, "rb") as file:
                        st.download_button(
                            label="Download Preliminary Excel",
                            data=file,
                            file_name=output_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

if st.button("Process Edited Excel"):
    edited_file = st.file_uploader("Upload Edited Excel File", type=["xlsx"], key="edited_file")
    if edited_file is not None:
        with st.spinner("Processing edited playlists..."):
            message, playlists = process_edited_excel(edited_file)
            st.write(message)

            if playlists:
                output_filename = "Final_Playlists.xlsx"
                with pd.ExcelWriter(output_filename) as writer:
                    for i, playlist in enumerate(playlists):
                        if not playlist.empty:
                            sheet_name = f"Playlist {i + 1}"[:31]
                            playlist.to_excel(writer, sheet_name=sheet_name, index=False)

                with open(output_filename, "rb") as file:
                    st.download_button(
                        label="Download Final Excel",
                        data=file,
                        file_name=output_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
