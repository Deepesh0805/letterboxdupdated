import requests
from bs4 import BeautifulSoup
import streamlit as st
import re
from PIL import Image, ImageDraw
import requests
from io import BytesIO
import plotly.express as px
import altair as alt

import sqlite3
import imdb
from imdb import IMDb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Create an instance of the IMDb class
ia = imdb.IMDb()

# Page layout
st.set_page_config(page_title="Letterboxd Stats", page_icon="🌎", layout="wide")

# Load CSS Style
with open('style.css') as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Connect to SQLite database
conn = sqlite3.connect('movies.db')
c = conn.cursor()

# Create table to store movie details
c.execute('''CREATE TABLE IF NOT EXISTS movies
             (username CHAR(50), year INTEGER, title TEXT, director TEXT, country TEXT, language TEXT, runtime INTEGER, genre TEXT, cast TEXT, rating FLOAT)''')

# Commit changes and close connection
conn.commit()

def get_year_movie_count(username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()

    # Query to get count of movies by year for a specific username
    c.execute('''SELECT year, COUNT(*) as num_movies FROM movies WHERE username = ? GROUP BY year''', (username,))
    rows = c.fetchall()

    # Create dictionary to store results
    movie_count_by_year = {}
    for row in rows:
        year = row[0]
        num_movies = row[1]
        movie_count_by_year[year] = num_movies

    conn.close()
    return movie_count_by_year

def get_user_stats(username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()

    # Calculate total runtime in hours for the given username
    c.execute("SELECT SUM(runtime) FROM movies WHERE username = ?", (username,))
    total_runtime_minutes = c.fetchone()[0]
    if total_runtime_minutes:
        total_runtime_hours = total_runtime_minutes / 60
        tot_hours = f"{total_runtime_hours:.2f} hours"
        tot_hours = round(tot_hours, 2)
    else:
        tot_hours = "No movies found for the user"

    # Calculate total number of distinct directors for the given username
    c.execute("SELECT COUNT(DISTINCT director) FROM movies WHERE username = ?", (username,))
    tot_dirs = c.fetchone()[0]

    # Calculate total number of distinct countries for the given username
    c.execute("SELECT COUNT(DISTINCT country) FROM movies WHERE username = ?", (username,))
    tot_countries = c.fetchone()[0]

    conn.close()

    return tot_hours, tot_dirs, tot_countries

def mask_to_circle(img):
    # Create a circular mask
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + img.size, fill=255)

    # Apply the circular mask to the image
    result = Image.new("RGBA", img.size, (255, 255, 255, 0))
    result.paste(img, (0, 0), mask)

    return result

# Function to scrape the HTML and extract basic details including favorite films and their links
def scrape_profile(username):
    url = f"https://letterboxd.com/{username}/"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Extracting basic details
    name = soup.find('meta', property='og:title')['content']
    bio = soup.find('meta', property='og:description')['content']
    image_url = soup.find('meta', property='og:image')['content']
    
    return name, bio, image_url

def get_movie_details(movie_link):
    response = requests.get(movie_link)
    soup = BeautifulSoup(response.content, 'html.parser')
    script_tag = soup.find('script', type='application/ld+json')
    if script_tag:
        image_url = re.search(r'"image":"(.*?)"', str(script_tag)).group(1)
        return image_url
    else:
        return None

def extract_movies(url):
    film_slugs = []
    movie_info = []
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    movie_containers = soup.find_all('li', class_='poster-container')
    
    # Loop through each movie container
    for container in movie_containers:
        # Find the div element with class 'poster' inside the container
        div_element = container.find('div', class_='poster')
        # Check if the div_element exists and has the 'data-film-slug' attribute
        if div_element and 'data-film-slug' in div_element.attrs:
            # Extract the value of the 'data-film-slug' attribute and append it to the list
            film_slugs.append(div_element['data-film-slug'])

    return film_slugs

def extract_all_movies(username):
    base_url = f"https://letterboxd.com/{username}/films/by/date-earliest/"
    all_movies = []
    page_num = 1
    while True:
        url = f"{base_url}page/{page_num}/"
        movies = extract_movies(url)
        if not movies:
            break
        all_movies.extend(movies)
        page_num += 1
    
    return all_movies

def fetch_movie_details(username, movie_titles, stop_flag, data_collection_text):
    ia = IMDb()

    conn = sqlite3.connect('movies.db')
    c = conn.cursor()

    # Check if the username already exists in the table
    c.execute("SELECT title FROM movies WHERE username = ? ORDER BY ROWID DESC LIMIT 1", (username,))
    last_movie_title = c.fetchone()

    if last_movie_title:
        last_movie_title = last_movie_title[0]
        try:
            last_movie_index = movie_titles.index(last_movie_title)
            movie_titles = movie_titles[last_movie_index + 1:]
        except ValueError:
            # If last movie not found in movie_titles, insert all movies
            pass

    total_films = len(movie_titles)
    i = 0

    for title in movie_titles:
        if stop_flag:
            break
        else:
          try:
            movie = ia.search_movie(title)[0]
            ia.update(movie)

            year = movie.get('year', '')
            director = ', '.join([person['name'] for person in movie.get('directors', [])])
            country = movie.get('countries', [])[0] if movie.get('countries') else ''
            language = movie.get('languages', [])[0] if movie.get('languages') else ''
            runtime = movie.get('runtimes', [])[0] if movie.get('runtimes', []) else None
            genre = ', '.join(movie.get('genres', []))
            cast = ', '.join([person['name'] for person in movie.get('cast', [])])
            rating = movie.get('rating', None)

            # Assuming you have defined progress_bar elsewhere
            progress_bar.progress((i + 1) / total_films)
            data_collection_text.text(f"Collecting your data {round(((i + 1) / total_films) * 100, 2)}%")

            c.execute("INSERT INTO movies (username, year, title, director, country, language, runtime, genre, cast, rating) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (username, year, title, director, country, language, runtime, genre, cast, rating))

            conn.commit()

            i += 1
          except Exception as e:
            print(f"Error fetching details for '{title}': {e}")

    conn.close()

def count_genre_entries(username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()

    # Define genre names
    genre_names = ["Action", "Adventure", "Animation", "Biography", "Comedy", "Crime", "Documentary", "Drama",
                   "Family", "Fantasy", "Film-Noir", "History", "Horror", "Music", "Musical", "Mystery", 
                   "Romance", "Sci-Fi", "Short", "Sport", "Thriller", "War", "Western"]

    # Initialize a dictionary to store counts for each genre
    genre_counts = {}

    # Count the number of entries for each genre containing the specified genre name
    for genre in genre_names:
        c.execute("SELECT COUNT(*) FROM movies WHERE username = ? AND genre LIKE ?", (username, f"%{genre}%"))
        count = c.fetchone()[0]
        genre_counts[genre] = count

    conn.close()

    return genre_counts

def get_top_countries(username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    # Fetch top 9 countries by count
    c.execute("SELECT country, COUNT(*) as count FROM movies WHERE username = ? GROUP BY country ORDER BY count DESC LIMIT 9", (username,))
    top_countries = c.fetchall()

    conn.close()

    top_countries_dict = {country: count for country, count in top_countries}

    return top_countries_dict

def get_top_languages(username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    # Fetch top 9 languages by count
    c.execute("SELECT language, COUNT(*) as count FROM movies WHERE username = ? GROUP BY language ORDER BY count DESC LIMIT 9", (username,))
    top_languages = c.fetchall()

    conn.close()

    top_languages_dict = {language: count for language, count in top_languages}

    return top_languages_dict

def get_top_directors(username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    # Fetch top 5 directors by count
    c.execute("SELECT director, COUNT(*) as count FROM movies WHERE username = ? GROUP BY director ORDER BY count DESC LIMIT 5", (username,))
    top_directors = c.fetchall()

    conn.close()

    top_directors_dict = {director: count for director, count in top_directors}

    return top_directors_dict

def get_top_actors(username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    # Fetch top 5 actors by count
    c.execute("SELECT cast, COUNT(*) as count FROM movies WHERE username = ? GROUP BY cast ORDER BY count DESC LIMIT 5", (username,))
    top_actors = c.fetchall()

    conn.close()

    top_actors_dict = {actor: count for actor, count in top_actors}

    return top_actors_dict

def get_top_movies(username, limit=5):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    # Fetch top movies by rating
    c.execute("SELECT title, rating FROM movies WHERE username = ? ORDER BY rating DESC LIMIT ?", (username, limit))
    top_movies = c.fetchall()

    conn.close()

    top_movies_dict = {title: rating for title, rating in top_movies}

    return top_movies_dict

def plot_year_movie_count(movie_count_by_year):
    years = list(movie_count_by_year.keys())
    counts = list(movie_count_by_year.values())
    data = pd.DataFrame({
        'Year': years,
        'Count': counts
    })
    chart = alt.Chart(data).mark_bar().encode(
        x='Year:O',
        y='Count:Q'
    ).properties(
        title='Number of Movies Watched by Year'
    )
    return chart

def plot_genre_distribution(genre_counts):
    labels = list(genre_counts.keys())
    sizes = list(genre_counts.values())
    colors = plt.cm.Paired(np.linspace(0, 1, len(labels)))

    fig, ax = plt.subplots()
    ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=140)
    ax.axis('equal')
    plt.title('Genre Distribution')

    return fig

def plot_top_countries(top_countries):
    countries = list(top_countries.keys())
    counts = list(top_countries.values())
    data = pd.DataFrame({
        'Country': countries,
        'Count': counts
    })
    chart = alt.Chart(data).mark_bar().encode(
        x='Country:O',
        y='Count:Q'
    ).properties(
        title='Top 9 Countries'
    )
    return chart

def plot_top_languages(top_languages):
    languages = list(top_languages.keys())
    counts = list(top_languages.values())
    data = pd.DataFrame({
        'Language': languages,
        'Count': counts
    })
    chart = alt.Chart(data).mark_bar().encode(
        x='Language:O',
        y='Count:Q'
    ).properties(
        title='Top 9 Languages'
    )
    return chart

def plot_top_directors(top_directors):
    directors = list(top_directors.keys())
    counts = list(top_directors.values())
    data = pd.DataFrame({
        'Director': directors,
        'Count': counts
    })
    chart = alt.Chart(data).mark_bar().encode(
        x='Director:O',
        y='Count:Q'
    ).properties(
        title='Top 5 Directors'
    )
    return chart

def plot_top_actors(top_actors):
    actors = list(top_actors.keys())
    counts = list(top_actors.values())
    data = pd.DataFrame({
        'Actor': actors,
        'Count': counts
    })
    chart = alt.Chart(data).mark_bar().encode(
        x='Actor:O',
        y='Count:Q'
    ).properties(
        title='Top 5 Actors'
    )
    return chart

def plot_top_movies(top_movies):
    movies = list(top_movies.keys())
    ratings = list(top_movies.values())
    data = pd.DataFrame({
        'Movie': movies,
        'Rating': ratings
    })
    chart = alt.Chart(data).mark_bar().encode(
        x='Movie:O',
        y='Rating:Q'
    ).properties(
        title='Top Movies by Rating'
    )
    return chart

def main():
    st.title("Letterboxd Stats")

    # Prompt user for Letterboxd username
    username = st.text_input("Enter your Letterboxd username", "")

    if username:
        # Scrape user profile
        name, bio, image_url = scrape_profile(username)
        
        # Display profile information
        st.header(name)
        st.write(bio)
        st.image(image_url)

        # Extract all movies watched by the user
        all_movies = extract_all_movies(username)

        # Set up data collection flag and text
        stop_flag = False
        data_collection_text = st.empty()
        progress_bar = st.progress(0)
        fetch_movie_details(username, all_movies, stop_flag, data_collection_text)

        # Get user statistics
        tot_hours, tot_dirs, tot_countries = get_user_stats(username)

        # Display user statistics
        st.write(f"Total hours of movies watched: {tot_hours}")
        st.write(f"Total number of directors: {tot_dirs}")
        st.write(f"Total number of countries: {tot_countries}")

        # Get movie count by year
        movie_count_by_year = get_year_movie_count(username)

        # Plot and display number of movies watched by year
        st.altair_chart(plot_year_movie_count(movie_count_by_year), use_container_width=True)

        # Get genre distribution
        genre_counts = count_genre_entries(username)

        # Plot and display genre distribution
        st.pyplot(plot_genre_distribution(genre_counts))

        # Get top countries
        top_countries = get_top_countries(username)

        # Plot and display top countries
        st.altair_chart(plot_top_countries(top_countries), use_container_width=True)

        # Get top languages
        top_languages = get_top_languages(username)

        # Plot and display top languages
        st.altair_chart(plot_top_languages(top_languages), use_container_width=True)

        # Get top directors
        top_directors = get_top_directors(username)

        # Plot and display top directors
        st.altair_chart(plot_top_directors(top_directors), use_container_width=True)

        # Get top actors
        top_actors = get_top_actors(username)

        # Plot and display top actors
        st.altair_chart(plot_top_actors(top_actors), use_container_width=True)

        # Get top movies
        top_movies = get_top_movies(username)

        # Plot and display top movies
        st.altair_chart(plot_top_movies(top_movies), use_container_width=True)

if __name__ == "__main__":
    main()
