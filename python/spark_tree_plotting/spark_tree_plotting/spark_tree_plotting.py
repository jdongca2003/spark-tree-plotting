from collections import OrderedDict
from json import loads, dumps
from pyspark import SparkContext

def generate_color_brew(n):
    """
    Generates an evenly distributed range
    of hue values in the HSV colour scale.

    Arguments:
    n -- an int with the number of hue values
         you want to obtain

    Returns:
    a python list with those hue values
    """
    hue_step = 360 / float(n)
    return [color * hue_step / 360.0 for color in range(n)]


def node_to_str(node, featureNames, categoryNames, classNames, numClasses, 
                nodeList, filled, round_leaves, colorBrew):
    """
    Generates a DOT-compatible string for a given tree node.
    Note that this function has side-effects, as node properties
    will be written to the nodeList argument without being
    explicitly returned (in fact, those side-effects are the
    key part of this function).

    This function is not meant to be used directly.

    Arguments:
    node -- a tree node (Python dict) as parsed from the JSON format

    featureNames -- a list with the feature names. This
                    is probably the same list you usually
                    pass to your VectorAssembler constructor

    categoryNames -- a dictionary with the featureNames that
                     are categorical as the keys, and the
                     different categories as the values.
                     This is probably the featureNames as key,
                     StringIndexerModel.labels attribute as value
                     for each categorical feature

    classNames -- a list with the class names for your target
                  column. This is probably the StringIndexerModel.labels
                  for your target column

    numClasses -- internal argument, obtained from the function
                  get_num_classes

    nodeList -- list that captures the side-effects for this function.
                It captures the node attributes

    filled -- boolean which indicates whether to fill nodes with colour
              or not. Color gamma will be the prediction class for each
              node, and color intensity the impurity at such node

    round_leaves -- boolean which indicates whether to represent leaf
                    nodes as ellipses rather than rectangles

    colorBrew -- list of hue values as generated by generate_color_brew()

    Returns:
    Just the node id as a string. The rest of the functionality
    are side-effects, inserted into nodeList
    """
    # classNames preparation:
    if classNames is None:
        class_name = node["prediction"]
        class_name_str = "Class #" + str(int(node["prediction"]))
    else:
        class_names = dict(enumerate(classNames))
        class_name = class_names[node["prediction"]]
        class_name_str = str(class_name)
    
    attributes = []

    # Names preparation (featureNames, categoryNames):
    if node["nodeType"] == "internal":
        
        if featureNames is None:
            feature_name = node["featureIndex"]
            feature_name_str = "Feature #" + str(feature_name)
        else:
            featureNames = dict(enumerate(featureNames))
            feature_name = featureNames[node["featureIndex"]]
            feature_name_str = str(feature_name)
        
        if categoryNames is None:
            if node["splitType"] == "categorical":
                list_of_categories_5_by_5 = []
                for i in range(0, len(node["leftCategories"]), 5):
                    list_of_categories_5_by_5.append(",".join([str(j) for j in node["leftCategories"][i:i+5]]))
                categories = "categories# " + "{" + "\\n".join(str(n) for n in list_of_categories_5_by_5) + "}"
        else:
            if node["splitType"] == "categorical":
                try:
                    category_names = dict(enumerate(categoryNames[feature_name]))
                    list_of_categories_5_by_5 = []
                    for i in range(0, len(node["leftCategories"]), 5):
                        list_of_categories_5_by_5.append(",".join([category_names[j] for j in node["leftCategories"][i:i+5]]))
                    categories = "{" + "\\n".join(n for n in list_of_categories_5_by_5) + "}"
                except KeyError:
                    list_of_categories_5_by_5 = []
                    for i in range(0, len(node["leftCategories"]), 5):
                        list_of_categories_5_by_5.append(",".join([str(j) for j in node["leftCategories"][i:i+5]]))
                    categories = "categories# " + "{" + "\\n".join(str(n) for n in list_of_categories_5_by_5) + "}"

        # For continuous split:
        if node["splitType"] == "continuous":
            label = """ label="Node ID %s\\n%s <= %.4f\\nImpurity = %.4f\\nGain = %.4f\\nPrediction = %s" """ % (node["id"],
                                                                                                                 feature_name_str,
                                                                                                                 node["threshold"],
                                                                                                                 node["impurity"],
                                                                                                                 node["gain"],
                                                                                                                 class_name_str
                                                                                                                )
        # For categorical split:
        else:
            label = """ label="Node ID %s\\n%s in %s\\nImpurity = %.4f\\nGain = %.4f\\nPrediction = %s" """ % (node["id"],
                                                                                                               feature_name_str,
                                                                                                               categories,
                                                                                                               node["impurity"],
                                                                                                               node["gain"],
                                                                                                               class_name_str
                                                                                                              )
    # Leaf node:
    else:
        label = """ label="Node ID %s\\nImpurity = %.4f\\nPrediction = %s" """ % (node["id"],
                                                                                  node["impurity"],
                                                                                  class_name_str
                                                                                 )
        if round_leaves is True:
            attributes.append("shape=ellipse")
            #nodeList.append(graph_string + "[shape=ellipse]") # Change leaf shape
    
    attributes.append(label)

    # Color adding:
    if filled is True:
        h = colorBrew[int(node["prediction"])]
        s = 1.0 - node["impurity"]
        attributes.append('fillcolor="%.4f,%.4f,%.4f"' % (h,s,1.0))
        #nodeList.append(graph_string + ' [fillcolor="%.4f,%.4f,%.4f"]' % (h,s,1.0))

    nodeList.append("%s [%s]" % (node["id"],
                                 ",".join(attributes)))

    return str(node["id"])

def get_num_classes(node):
    """
    Gets the number of different classes that 
    the tree predicts.

    Arguments:
    node --  the root node for the tree

    Returns:
    the number of classes, as an integer
    """
    nodes_to_explore = [node]
    classes = set()
    while len(nodes_to_explore) > 0:
        if len(nodes_to_explore) == 0:
            break
        current_node = nodes_to_explore.pop()
        classes.add(current_node["prediction"])
        
        if current_node["nodeType"] == "internal":
            nodes_to_explore.append(current_node["leftChild"])
            nodes_to_explore.append(current_node["rightChild"])
    return int(max(list(classes)) + 1)

def add_node_ids(node):
    """
    Adds node IDs to the tree (the recursive Python dict)
    in a breadth-first fasion.

    Arguments:
    node --  the root node for the tree

    Returns:
    the same tree (Python dict), but with a new key for
    each node (the ID)
    """
    nodes_to_explore = [node]
    counter = -1
    while len(nodes_to_explore) > 0:
        if len(nodes_to_explore) == 0:
            break
        current_node = nodes_to_explore.pop(0)
        counter += 1
        current_node["id"] = counter
        #classes.add(current_node["prediction"])
        
        if current_node["nodeType"] == "internal":
            nodes_to_explore.append(current_node["leftChild"])
            nodes_to_explore.append(current_node["rightChild"])
    return node

def relations_to_str(node, featureNames=None, categoryNames=None, classNames=None, 
                     numClasses=None, nodeList=None, filled=True, roundLeaves=True,
                     color_brew=None):
    """
    Generates the DOT-compatible strings to create the tree
    structure.

    This function is not meant to be used directly.

    Arguments:
    node -- a tree node (Python dict) as parsed from the JSON format

    featureNames -- a list with the feature names. This
                    is probably the same list you usually
                    pass to your VectorAssembler constructor

    categoryNames -- a dictionary with the featureNames that
                     are categorical as the keys, and the
                     different categories as the values.
                     This is probably the featureNames as key,
                     StringIndexerModel.labels attribute as value 
                     for each categorical feature

    classNames -- a list with the class names for your target
                  column. This is probably the StringIndexerModel.labels
                  for your target column

    numClasses -- internal argument, obtained from the function
                  get_num_classes

    nodeList -- list that captures the side-effects for the node_to_string function.
                It captures the node attributes

    filled -- boolean which indicates whether to fill nodes with colour
              or not. Color gamma will be the prediction class for each
              node, and color intensity the impurity at such node

    roundLeaves -- boolean which indicates whether to represent leaf
                    nodes as ellipses rather than rectangles

    color_brew -- list of hue values as generated by generate_color_brew()

    Returns:
    A Python list of strings with the relationships in DOT format
    """
    nodes_to_explore = [node]
    relations = []
    while len(nodes_to_explore) > 0:
        if len(nodes_to_explore) == 0:
            break
        current_node = nodes_to_explore.pop()
        if current_node["nodeType"] == "leaf":
            continue
        relations.append(node_to_str(current_node, featureNames, categoryNames, 
                                     classNames, numClasses, nodeList, filled, roundLeaves, color_brew) 
                         + "->" 
                         + node_to_str(current_node["leftChild"], featureNames, categoryNames, 
                                       classNames, numClasses, nodeList, filled, roundLeaves, color_brew) 
                         + '[labeldistance=2.5, labelangle=45., headlabel="True"]' 
                         + "\n")
        nodes_to_explore.append(current_node["leftChild"])
        
        relations.append(node_to_str(current_node, featureNames, categoryNames, 
                                     classNames, numClasses, nodeList, filled, roundLeaves, color_brew) 
                         + "->" 
                         + node_to_str(current_node["rightChild"], featureNames, categoryNames, 
                                       classNames, numClasses, nodeList, filled, roundLeaves, color_brew) 
                         + '[labeldistance=2.5, labelangle=-45., headlabel="False"]' 
                         + "\n")
        nodes_to_explore.append(current_node["rightChild"])
    return relations

def generate_tree_json(DecisionTreeClassificationModel, withNodeIDs=False):
    """
    Creates a recursive JSON string with the tree structure of a Spark's fitted
    DecisionTreeClassificationModel. Each node is defined by its attributes 
    (such as split rule, impurity...), and also its children, which are also 
    nodes with their own attributes and children (unitl a leaf node is reached).

    This JSON is meant to be used to plot the tree with whatever plotting
    library which is compatible with the JSON format.

    Arguments:
    DecisionTreeClassificationModel -- a pyspark.ml.classification.DecisionTreeClassificationModel
                                       instance
    
    withNodeIDs -- boolean that indicates whether to add IDs (increasing in breadth-first
                   fashion) to the tree nodes

    Returns:
    a JSON string with the formatted tree
    """
    sc = SparkContext.getOrCreate()

    json_tree = sc._jvm.com.vfive.spark.ml.SparkMLTree(DecisionTreeClassificationModel._java_obj).toJsonPlotFormat()

    if withNodeIDs:
        json_tree = dumps(add_node_ids(loads(json_tree, object_pairs_hook=OrderedDict)), indent=2)

    return json_tree

def export_graphviz(DecisionTreeClassificationModel, featureNames=None, categoryNames=None, classNames=None,
                   filled=True, roundedCorners=True, roundLeaves=True):
    """
    Generates a DOT string out of a Spark's fitted DecisionTreeClassificationModel, which
    can be drawn with any library capable of handling the DOT format.

    If you want to plot in a single step, please use the function plot_tree().

    Arguments:
    DecisionTreeClassificationModel -- a pyspark.ml.classification.DecisionTreeClassificationModel
                                       instance

    featureNames -- a list with the feature names. This
                    is probably the same list you usually
                    pass to your VectorAssembler constructor

    categoryNames -- a dictionary with the featureNames that
                     are categorical as the keys, and the
                     different categories as the values.
                     This is probably the featureNames as key,
                     StringIndexerModel.labels attribute as value
                     for each categorical feature

    classNames -- a list with the class names for your target
                  column. This is probably the StringIndexerModel.labels
                  for your target column

    filled -- boolean which indicates whether to fill nodes with colour
              or not. Color gamma will be the prediction class for each
              node, and color intensity the impurity at such node

    roundedCorners -- boolean which indicates whether to round 
                      rectangle corners for the nodes

    roundLeaves -- boolean which indicates whether to represent leaf
                    nodes as ellipses rather than rectangles

    Returns:
    a DOT string ready to be processed by any DOT handling library
    """
    tree_dict = loads(generate_tree_json(DecisionTreeClassificationModel, withNodeIDs=False))
    num_classes = get_num_classes(tree_dict)
    color_brew = generate_color_brew(num_classes)
    node_list = []
    tree_dict_with_id = add_node_ids(tree_dict)

    graph = relations_to_str(tree_dict_with_id,
                             featureNames=featureNames, 
                             categoryNames=categoryNames, 
                             classNames=classNames, 
                             numClasses=num_classes,
                             nodeList=node_list,
                             filled=filled,
                             roundLeaves=roundLeaves,
                             color_brew=color_brew)
    node_properties = "\n".join(node_list)
    filled_and_rounded = []
    if filled:
        filled_and_rounded.append("filled")
    if roundedCorners:
        filled_and_rounded.append("rounded")
    dot_string = """digraph Tree {
                    node [shape=box style="%s"]
                    subgraph body {
                    %s
                    %s}
                    }""" % (",".join(filled_and_rounded), "".join(graph), node_properties)
    return dot_string


def plot_tree(DecisionTreeClassificationModel, featureNames=None, categoryNames=None, classNames=None,
              filled=True, roundedCorners=True, roundLeaves=True):
    """
    Draws a Spark's fitted DecisionTreeClassificationModel in png format. If you are
    using Jupyter, this function can be easily used alongside Ipython.display in order
    to draw a tree in Jupyter:

        from spark_tree_plotting import plot_tree
        from IPython.display import Image

        Image(plot_tree(my_DecisionTreeClassificationModel))

    Note that this function requires pydot3 to be installed.

    Arguments:
    DecisionTreeClassificationModel -- a pyspark.ml.classification.DecisionTreeClassificationModel
                                       instance

    featureNames -- a list with the feature names. This
                    is probably the same list you usually
                    pass to your VectorAssembler constructor

    categoryNames -- a dictionary with the featureNames that
                     are categorical as the keys, and the
                     different categories as the values.
                     This is probably the featureNames as key,
                     StringIndexerModel.labels attribute as value
                     for each categorical feature

    classNames -- a list with the class names for your target
                  column. This is probably the StringIndexerModel.labels
                  for your target column

    filled -- boolean which indicates whether to fill nodes with colour
              or not. Color gamma will be the prediction class for each
              node, and color intensity the impurity at such node

    roundedCorners -- boolean which indicates whether to round 
                      rectangle corners for the nodes

    roundLeaves -- boolean which indicates whether to represent leaf
                    nodes as ellipses rather than rectangles

    Returns:
    a PNG string, which can be displayed in Jupyter/any webpage and/or
    be saved to disk
    """

    try:
        from pydot import graph_from_dot_data
    except ImportError:
        raise ImportError(
            "This function requires pydot dot be installed. You can easily install it with pip install pydot"
            )

    graph = graph_from_dot_data(export_graphviz(DecisionTreeClassificationModel,
                                               featureNames=featureNames,
                                               categoryNames=categoryNames,
                                               classNames=classNames,
                                               filled=filled,
                                               roundedCorners=roundedCorners,
                                               roundLeaves=roundLeaves
                                               )
                               )
    if type(graph) is list:
        plot = graph[0].create_png()
    else:
        plot = graph.create_png()
    return plot
    
