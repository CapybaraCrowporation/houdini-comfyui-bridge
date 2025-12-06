# First Steps 3

## Improvements

To preview a generated image without having to go up a level to the face of the compound graph node, we can use a Preview node inside of the compound graph:

1. Go to our inner graph used to generate the shiba.

2. Create a ComfyUI Graph Preview node

3. Plug the output of **VAE_Decode** node into the Preview node

4. Put a display flag onto this preview node

   ![Create ComfyUI Graph Preview Node](images/first_steps_3_preview_node.png)

5. Click "**Generate Preview**" button

   ![Generate Preview Button](images/first_steps_3_generate_button.png)

And there you have it! Preview nodes are handy for cooking results of different stages of the compound graph

![Preview Result with Shiba](images/first_steps_3_preview_result.png)
