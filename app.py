import random
from openai import ChatCompletion
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

def validate_playlist_rules(data, num_playlists, tracks_per_playlist):
    """Validate if the playlists can be created based on the rules."""
    unique_artists = data['artist'].nunique()
    total_tracks = len(data)

    max_tracks_by_artist = 3 * unique_artists * num_playlists
    if total_tracks < tracks_per_playlist * num_playlists:
        return False, "Insufficient tracks for the requested playlists."
    if max_tracks_by_artist < tracks_per_playlist * num_playlists:
        return False, "Too many restrictions for the available tracks."
    return True, "Valid playlist configuration."

def generate_playlists(data, num_playlists, tracks_per_playlist):
    """Generate playlists based on the rules."""
    playlists = []
    for _ in range(num_playlists):
        playlist = []
        used_artists = {}
        remaining_tracks = data.copy()

        while len(playlist) < tracks_per_playlist:
            valid_tracks = remaining_tracks[~remaining_tracks['artist'].isin(
                [artist for artist, count in used_artists.items() if count >= 3]
            )]

            if valid_tracks.empty:
                break

            selected_track = valid_tracks.sample(1).iloc[0]
            playlist.append(selected_track)

            # Update artist usage and remaining tracks
            artist = selected_track['artist']
            used_artists[artist] = used_artists.get(artist, 0) + 1
            remaining_tracks = remaining_tracks[remaining_tracks['isrc'] != selected_track['isrc']]

        playlists.append(pd.DataFrame(playlist))
    return playlists

def suggest_playlist_names(num_playlists):
    """Use OpenAI API to suggest playlist names."""
    completion = ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Suggest creative playlist names based on themes of love and music."},
            {"role": "user", "content": f"Generate {num_playlists} playlist names that are fun and unique."}
        ]
    )
    return [choice['message']['content'] for choice in completion['choices']]

def process_playlists(file, num_playlists, tracks_per_playlist):
    """Main function to process playlists and return results."""
    data = pd.read_excel(file, sheet_name='Songs That Speak of Love')[['Recording Artist', 'Recording Title', 'ISRCs']]
    data.rename(columns={
        'Recording Artist': 'artist',
        'Recording Title': 'title',
        'ISRCs': 'isrc'
    }, inplace=True)
    data.dropna(inplace=True)

    is_valid, message = validate_playlist_rules(data, num_playlists, tracks_per_playlist)
    if not is_valid:
        return message, None

    playlists = generate_playlists(data, num_playlists, tracks_per_playlist)
    playlist_names = suggest_playlist_names(num_playlists)

    results = []
    for i, playlist in enumerate(playlists):
        playlist['Playlist Name'] = playlist_names[i]
        results.append(playlist[['Playlist Name', 'artist', 'title']])

    return "Playlists generated successfully!", results

# Streamlit Interface
st.title("Playlist Generator")
st.write("Upload an Excel file to generate playlists with specific rules.")

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])
num_playlists = st.number_input("Number of Playlists", min_value=1, value=3, step=1)
tracks_per_playlist = st.number_input("Tracks per Playlist", min_value=1, value=20, step=1)

if uploaded_file is not None:
    with st.spinner("Processing playlists..."):
        message, playlists = process_playlists(uploaded_file, num_playlists, tracks_per_playlist)

    st.write(message)

    if playlists:
        for i, playlist in enumerate(playlists):
            st.subheader(f"Playlist {i + 1}")
            st.write(playlist.to_html(index=False, escape=False), unsafe_allow_html=True)
