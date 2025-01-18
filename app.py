import random
import openai
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import os

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
    for _ in range(num_playlists):
        playlist = []
        used_artists = {}
        used_isrcs = set()
        remaining_tracks = data.copy()

        while len(playlist) < tracks_per_playlist:
            valid_tracks = remaining_tracks[~remaining_tracks['artist'].isin(
                [artist for artist, count in used_artists.items() if count >= 3]
            ) & ~remaining_tracks['isrc'].isin(used_isrcs)]

            if valid_tracks.empty:
                break

            if 'streams' in valid_tracks.columns:
                # Use weighted sampling based on the 'streams' column
                valid_tracks['weight'] = valid_tracks['streams'] / valid_tracks['streams'].sum()
                selected_track = valid_tracks.sample(1, weights='weight').iloc[0]
            else:
                # If no 'streams' column, select randomly
                selected_track = valid_tracks.sample(1).iloc[0]

            playlist.append(selected_track)

            # Update artist usage, used ISRCs, and remaining tracks
            artist = selected_track['artist']
            used_artists[artist] = used_artists.get(artist, 0) + 1
            used_isrcs.add(selected_track['isrc'])
            remaining_tracks = remaining_tracks[remaining_tracks['isrc'] != selected_track['isrc']]

        playlists.append(pd.DataFrame(playlist))
    return playlists

def suggest_playlist_names(num_playlists):
    """Use OpenAI API to suggest playlist names."""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Suggest creative playlist names based on themes of love and music."},
                {"role": "user", "content": f"Generate {num_playlists} playlist names that are fun and unique."}
            ]
        )
        return [msg['content'] for msg in response['choices']]
    except Exception as e:
        return [f"Playlist {i + 1}" for i in range(num_playlists)]

def process_playlists(file, num_playlists, tracks_per_playlist):
    """Main function to process playlists and return results."""
    try:
        data = pd.read_excel(file, sheet_name=0)
    except Exception as e:
        return f"Error reading Excel file: {e}", None

    required_columns = ['Recording Artist', 'Recording Title', 'ISRC']
    optional_columns = ['Number of Streams']

    if not all(col in data.columns for col in required_columns):
        return ("The uploaded file does not contain the required columns: "
                "'Recording Artist', 'Recording Title', 'ISRC'. Please check your file and try again."), None

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
        return message, None

    playlists = generate_playlists(data, num_playlists, tracks_per_playlist)
    playlist_names = suggest_playlist_names(num_playlists)

    # Ensure there are enough names for the playlists
    if len(playlist_names) < len(playlists):
        playlist_names += [f"Playlist {i + 1}" for i in range(len(playlist_names), len(playlists))]

    results = []
    for i, playlist in enumerate(playlists):
        playlist['Playlist Name'] = playlist_names[i]
        results.append(playlist[['Playlist Name', 'artist', 'title', 'isrc'] + (['streams'] if 'streams' in data.columns else [])])

    return "Playlists generated successfully!", results

def save_to_excel(playlists, output_filename):
    """Save playlists to an Excel file with each playlist as a separate sheet."""
    with pd.ExcelWriter(output_filename) as writer:
        for i, playlist in enumerate(playlists):
            playlist.to_excel(writer, sheet_name=f"Playlist {i + 1}", index=False)

# Streamlit Interface
st.title("Playlist Generator")
st.write("Upload an Excel file to generate playlists with specific rules.")

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])
num_playlists = st.number_input("Number of Playlists", min_value=1, value=3, step=1)
tracks_per_playlist = st.number_input("Tracks per Playlist", min_value=1, value=20, step=1)

if st.button("Create Playlists"):
    if uploaded_file is not None:
        with st.spinner("Processing playlists..."):
            message, playlists = process_playlists(uploaded_file, num_playlists, tracks_per_playlist)

        st.write(message)

        if playlists:
            for i, playlist in enumerate(playlists):
                st.subheader(f"Playlist {i + 1}")
                st.write(playlist.to_html(index=False, escape=False), unsafe_allow_html=True)

            # Add a download button for the Excel file
            output_filename = "playlists.xlsx"
            save_to_excel(playlists, output_filename)
            with open(output_filename, "rb") as file:
                st.download_button(
                    label="Download Playlists as Excel",
                    data=file,
                    file_name=output_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.error("Error: Archivo con data menor a tus solicitud. Ajusta la cantidad de playlists y tracks e intentalo de nuevo.")
