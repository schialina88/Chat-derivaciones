import streamlit as st

from logic import load_data, answer_query

st.set_page_config(page_title="Chat Estudios Bioquimicos", page_icon="🧪", layout="centered")

st.title("🧪 Chat de Estudios Bioquimicos")
st.caption("Pregunta por nombre de estudio, codigo o laboratorio. Ej: \"demora de ACTH\", \"muestra para HIV\".")

data = load_data()

if "history" not in st.session_state:
    st.session_state.history = []

for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

query = st.chat_input("Escribi tu consulta...")

if query:
    st.session_state.history.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    response = answer_query(data, query)

    st.session_state.history.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.markdown(response)
