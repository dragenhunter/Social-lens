import pandas as pd, streamlit as st
from storage import api_client

st.title("Instagram Scraper Dashboard")

st.subheader("Profiles")
try:
	profiles = api_client.fetch_profiles_sync()
	df_profiles = pd.DataFrame(profiles if isinstance(profiles, list) else [])
	st.dataframe(df_profiles)
except Exception as e:
	st.error(f"Failed to load profiles: {e}")

st.subheader("Posts")
try:
	posts = api_client.fetch_posts_sync()
	df_posts = pd.DataFrame(posts if isinstance(posts, list) else [])
	st.dataframe(df_posts)
except Exception as e:
	st.error(f"Failed to load posts: {e}")

st.subheader("Post History (Diffs)")
try:
	history = api_client.fetch_post_history_sync()
	df_history = pd.DataFrame(history if isinstance(history, list) else [])
	st.dataframe(df_history)
except Exception as e:
	st.error(f"Failed to load post history: {e}")
