from flask import Flask, render_template, request
from threads_api.src.threads_api import ThreadsAPI
import asyncio
import os
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO

app = Flask(__name__, static_url_path='/static')

# Asynchronously gets the user ID from a username
async def get_user_id_from_username(api, username):
    user_id = await api.get_user_id_from_username(username)
    return user_id

async def get_user_profile_info(username):
    api = ThreadsAPI()
    user_id = await api.get_user_id_from_username(username)

    if user_id:
        user_profile = await api.get_user_profile(user_id)
        await api.close_gracefully()
        return user_profile
    else:
        await api.close_gracefully()
        return None

async def get_user_threads(username):
    api = ThreadsAPI()
    user_id = await api.get_user_id_from_username(username)
    if user_id:
        threads = await api.get_user_threads(user_id)
        if threads:
            # Fetch likes for each thread
            likes_tasks = []
            for thread in threads:
                post_url = thread['thread_items'][0]['post']['code']
                post_code = post_url.split('/')[-1]
                likes_task = get_post_likes_for_thread(post_code)
                likes_tasks.append(likes_task)
            likes_results = await asyncio.gather(*likes_tasks)

            # Assign post likes results to each thread
            for thread, likes in zip(threads, likes_results):
                thread['likes'] = likes

        await api.close_gracefully()
        return threads
    else:
        await api.close_gracefully()
        return None

# Asynchronously fetches user profile, threads, and top engaged friends
async def fetch_user_data(api, username):
    user_id = await get_user_id_from_username(api, username)
    if user_id:
        user_profile = await api.get_user_profile(user_id)
        user_threads = await api.get_user_threads(user_id)
        if user_threads:
            # Fetch likes for each thread concurrently
            likes_tasks = [get_post_likes_for_thread(api, thread['thread_items'][0]['post']['code']) for thread in user_threads]
            likes_results = await asyncio.gather(*likes_tasks)

            # Assign post likes results to each thread
            for thread, likes in zip(user_threads, likes_results):
                thread['likes'] = likes

            # Get the top 10 engaged friends
            top_10_friends = await get_top_engaged_friends(username, user_threads)
        else:
            top_10_friends = []
    else:
        user_profile = None
        user_threads = []
        top_10_friends = []

    return user_id, user_profile, user_threads, top_10_friends



# New function to get the top 10 engaged friends for a user
async def get_top_engaged_friends(username, user_threads):
    friends_likes = {}
    friends_profile_pics = {}  # Dictionary to store profile_pic_url for each friend

    for thread in user_threads:
        for like_info in thread['likes']:
            friend_username = like_info['username']
            if friend_username != username:  # Exclude the original user from the list
                if friend_username in friends_likes:
                    friends_likes[friend_username] += 1
                else:
                    friends_likes[friend_username] = 1

                # Store the profile_pic_url for the friend
                if friend_username not in friends_profile_pics:
                    friends_profile_pics[friend_username] = like_info.get('profile_pic_url')

    # Sort the friends by the number of likes in descending order
    sorted_friends_likes = sorted(friends_likes.items(), key=lambda x: x[1], reverse=True)

    # Get the top 10 friends along with their profile_pic_url
    top_10_friends = [(friend[0], friends_profile_pics.get(friend[0])) for friend in sorted_friends_likes[:10]]

    return top_10_friends

def create_result_image(username, user_id, follower_count, top_10_friends, profile_pic_url=None):
    image_width = 700
    image_height = 250
    profile_pic_size = 98
    friend_pic_size = 50

    # Load the background image (replace 'background.jpg' with the path to your background image file)
    background_image = Image.open("background.png")
    background_image = background_image.resize((image_width, image_height))

    # Create a new image with the background image
    image = Image.new("RGB", (image_width, image_height))
    image.paste(background_image, (0, 0))

    draw = ImageDraw.Draw(image)

    # Load a font (replace 'arial.ttf' with the path to your desired font file)
    font_path = "arial.ttf"
    font_size = 32
    font_sizer = 14
    font_super_small = 12
    font = ImageFont.truetype(font_path, font_size)
    font_two = ImageFont.truetype(font_path, font_sizer)
    font_three = ImageFont.truetype(font_path, font_super_small)

    # Draw the username, user ID, and follower count on the image
    text_color = (188, 188, 188)  # You may change the text color to match the background image
    text_color_grey = (92, 92, 92)  # You may change the text color to match the background image
    username_text = f"{username}"
    user_id_text = f"{user_id}"
    follower_count_text = f"Followers: {format(follower_count, ',')}"
    draw.text((180, 35), username_text, fill=text_color, font=font)
    draw.text((190, 82), follower_count_text, fill=text_color_grey, font=font_two)  # Adjust the vertical position as needed

    # Your Profile Picture
    if profile_pic_url:
        try:
            response = requests.get(profile_pic_url)
            profile_pic = Image.open(BytesIO(response.content))
            profile_pic = profile_pic.resize((profile_pic_size, profile_pic_size))
            mask = Image.new("L", profile_pic.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse([(0, 0), profile_pic.size], fill=255)
            profile_pic.putalpha(mask)
            image.paste(profile_pic, (50, 25), profile_pic)  # Adjust the coordinates to place your profile picture
        except Exception as e:
            print(f"Error loading your profile picture: {e}")

    # Draw the top 10 friends and their profile pictures on the image
    y_offset = 145
    x_offset = 50  # Starting from 50 pixels in from the left

    for index, (friend, friend_profile_pic_url) in enumerate(top_10_friends):
        # Load the friend's profile picture and paste it on the image if available
        if friend_profile_pic_url:
            try:
                response = requests.get(friend_profile_pic_url)
                friend_profile_pic = Image.open(BytesIO(response.content))
                friend_profile_pic = friend_profile_pic.resize((friend_pic_size, friend_pic_size))
                mask = Image.new("L", friend_profile_pic.size, 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse([(0, 0), friend_profile_pic.size], fill=255)
                friend_profile_pic.putalpha(mask)
                image.paste(friend_profile_pic, (x_offset, y_offset),
                            friend_profile_pic)  # Adjust the coordinates to place friends' profile pictures
            except Exception as e:
                print(f"Error loading profile picture for {friend}: {e}")

        x_offset += friend_pic_size + 10  # Add 10 pixels spacing between images

    # Save the image
    image_path = f"static/{username}_result_image.png"
    image.save(image_path)

    return image_path

# Define a route to handle the form submission
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form['username']

        # Asynchronously run the functions and get the results
        async def main():
            api = ThreadsAPI()

            # Fetch user data asynchronously
            user_id, user_profile, user_threads, top_10_friends = await fetch_user_data(api, username)

            # Close the API connection after fetching data
            await api.close_gracefully()

            if user_threads:
                follower_count = user_profile.get('follower_count', 0)
                profile_pic_url = user_profile.get('profile_pic_url')

                # Create the result image
                result_image_path = create_result_image(username, user_id, follower_count, top_10_friends, profile_pic_url=profile_pic_url)

                return render_template('result.html', username=username, user_id=user_id, threads=user_threads, friends_list=top_10_friends, image_path=result_image_path, user_profile=user_profile)  # Pass user_profile to the template

            return render_template('result.html', username=username, user_id=user_id, threads=user_threads, user_profile=user_profile)  # Pass user_profile to the template

        return asyncio.run(main())

    return render_template('index.html')

# Asynchronously gets the likes for a post
async def get_post_likes_for_thread(api, post_code):
    post_id = await api.get_post_id_from_url(f"https://www.threads.net/t/{post_code}")
    if post_id:
        likes = await api.get_post_likes(post_id)
        number_of_likes_to_display = 50
        return likes[:number_of_likes_to_display]
    return []

if __name__ == '__main__':
    app.run(debug=True)

