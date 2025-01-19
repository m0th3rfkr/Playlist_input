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

def analyze_playlist_theme(song_titles, language):
    """Analyze the playlist theme using OpenAI."""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"Analyze the theme of the following playlist songs in {language}."},
                {"role": "user", "content": ", ".join(song_titles)}
            ]
        )
        if 'choices' in response:
            return response['choices'][0]['message']['content'].strip()
        else:
            return "Unknown Theme"
    except Exception as e:
        st.error(f"Error with OpenAI API: {e}")
        return "Unknown Theme"

def suggest_playlist_names(theme, inspiration_titles, num_playlists, language, adjectives, slang):
    """Use OpenAI API to suggest playlist names based on the theme."""
    try:
        adjective_list = ", ".join(adjectives) if adjectives else "fun and unique"
        inspiration_titles_text = random.choice(inspiration_titles) if inspiration_titles else ""
        slang_text = f"using {slang} slang." if slang else ""

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"Suggest creative playlist names based on the theme: '{theme}' in {language}. {slang_text}"},
                {"role": "user", "content": f"Use this inspiration: '{inspiration_titles_text}'. Generate {num_playlists} playlist names that are {adjective_list}."}
            ]
        )
        if 'choices' in response:
            playlist_names = response['choices'][0]['message']['content'].split("\n")
            return [name.split(".", 1)[-1].strip().strip('"') for name in playlist_names if name.strip()][:num_playlists]
        else:
            st.error("Unexpected response format from OpenAI API.")
            return [f"Playlist {i + 1}" for i in range(num_playlists)]
    except Exception as e:
        st.error(f"Error with OpenAI API: {e}")
        return [f"Playlist {i + 1}" for i in range(num_playlists)]

def process_playlists(file, num_playlists, tracks_per_playlist, language, use_openai, adjectives, slang):
    """Main function to process playlists and return results."""
    try:
        data = pd.read_excel(file, sheet_name=0)
        inspiration_data = pd.read_excel(file, sheet_name="Playlist Titles")
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

    if use_openai:
        song_titles = [track['title'] for playlist in playlists for _, track in playlist.iterrows()]
        theme = analyze_playlist_theme(song_titles, language)
        inspiration_titles = inspiration_data['Playlist Titles'].dropna().tolist()
        playlist_names = suggest_playlist_names(theme, inspiration_titles, num_playlists, language, adjectives, slang)
        if len(playlist_names) < len(playlists):
            playlist_names += [f"Playlist {i + 1}" for i in range(len(playlist_names), len(playlists))]
    else:
        playlist_names = [f"Playlist {i + 1}" for i in range(num_playlists)]

    results = []
    for i, playlist in enumerate(playlists):
        playlist_key = f"playlist_{i}"
        if playlist_key not in st.session_state:
            st.session_state[playlist_key] = playlist.copy()

        playlist_name_key = f"playlist_name_{i}"
        if playlist_name_key not in st.session_state:
            st.session_state[playlist_name_key] = playlist_names[i]

        new_name = st.text_input(f"Edit Playlist Name for Playlist {i + 1}",
                                 value=st.session_state.get(playlist_name_key),
                                 key=playlist_name_key)

        st.session_state[playlist_name_key] = new_name

        playlist['Playlist Name'] = st.session_state[playlist_name_key]

        exclude_keys = [f"exclude_{i}_{j}" for j in range(len(playlist))]
        for j, exclude_key in enumerate(exclude_keys):
            if exclude_key not in st.session_state:
                st.session_state[exclude_key] = False
            playlist.loc[j, 'Exclude from Excel'] = st.checkbox(
                f"Exclude track {j + 1} from Playlist {i + 1}",
                key=exclude_key,
                value=st.session_state[exclude_key]
            )

        results.append(playlist[['Playlist Name', 'artist', 'title', 'isrc', 'Exclude from Excel'] + (['streams'] if 'streams' in data.columns else [])])

    return "Playlists generated successfully!", results

def save_to_excel(playlists, output_filename):
    """Save playlists to an Excel file with each playlist as a separate sheet."""
    with pd.ExcelWriter(output_filename) as writer:
        for i, playlist in enumerate(playlists):
            filtered_playlist = playlist[~playlist['Exclude from Excel']]
            if not filtered_playlist.empty:
                sheet_name = re.sub(r'[\\/*?:\[\]]', '_', filtered_playlist['Playlist Name'].iloc[0])[:31]  # Ensure sheet name is valid
                filtered_playlist.to_excel(writer, sheet_name=sheet_name, index=False)

# Streamlit Interface
st.title("Playlist Generator")
st.write("Upload an Excel file to generate playlists with specific rules.")

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])
use_openai = st.checkbox("Use OpenAI for Playlist Names")
adjectives = []
adjectives_file = "adjectives.txt"
slang_file = "slang.txt"
use_slang = False
slang = None

if use_openai:
    try:
        with open(adjectives_file, "r") as file:
            adjectives_list = [line.strip() for line in file.readlines()]
        adjectives = st.multiselect("Select adjectives for playlist names", adjectives_list)
        user_adjective = st.text_input("Or write your own adjective")
        if user_adjective:
            adjectives.append(user_adjective)
    except FileNotFoundError:
        st.error(f"Adjective file '{adjectives_file}' not found.")

    language = st.selectbox("Select Language for Playlist Names", ["English", "Spanish", "French", "German"])

    use_slang = st.checkbox("Enable Slang Role")
    if use_slang:
        try:
            with open(slang_file, "r") as file:
                slang_list = [line.strip() for line in file.readlines()]
            slang = st.selectbox("Select Slang for Playlist Names", slang_list)
        except FileNotFoundError:
            st.error(f"Slang file '{slang_file}' not found.")

num_playlists = st.number_input("Number of Playlists", min_value=1, value=3, step=1)
tracks_per_playlist = st.number_input("Tracks per Playlist", min_value=1, value=20, step=1)

if st.button("Create Playlists"):
    if uploaded_file is not None:
        with st.spinner("Processing playlists..."):
            message, playlists = process_playlists(uploaded_file, num_playlists, tracks_per_playlist, language if use_openai else None, use_openai, adjectives, slang)

        st.write(message)

        if playlists:
            for i, playlist in enumerate(playlists):
                st.subheader(f"{playlist['Playlist Name'].iloc[0]}")
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
